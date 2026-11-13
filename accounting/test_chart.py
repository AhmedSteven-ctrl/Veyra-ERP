"""اختبارات دليل الحسابات: البيانات، التحميل والترقية، الحسابات الافتراضية، القيود، الأرصدة، الفورمز،
الاستيراد والتصدير، الشاشات والصلاحيات، وأمر load_chart."""
import csv
import io
import re
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from accounting.chart import (DEFAULT_ROLE_CODES, LEGACY_CHART, account_balances, account_for, balance_for_display,
                              broad_type, delete_blockers, export_csv, import_csv, load_default_chart, role_usage,
                              suggest_parent, upgrade_legacy_accounts)
from accounting.chart_data import CHART_ROWS
from accounting.forms import AccountForm
from accounting.models import Account, AccountMapping, Journal, JournalEntry, JournalLine
from accounting.services import _post, ensure_chart, post_sale, trial_balance
from core.management.commands.seed_modules import Command as SeedModules
from core.models import Company, CompanyModule, Module, Partner
from inventory.models import Product, Warehouse
from purchasing.models import PurchaseLine, PurchaseOrder
from purchasing.services import pay_order, receive_order
from sales.models import SalesLine, SalesOrder

DIGIT_CLASS = {"1": "asset", "2": "liability", "3": "equity", "4": "income", "5": "expense"}
GROUPS = {row[0]: row[6] for row in CHART_ROWS}


# ============================== بيانات الدليل (من غير قاعدة بيانات) ==============================
class ChartDataTests(SimpleTestCase):
    def test_132_unique_six_digit_accounts(self):
        codes = [row[0] for row in CHART_ROWS]
        self.assertEqual((len(codes), len(set(codes))), (132, 132))
        self.assertTrue(all(re.fullmatch(r"\d{6}", c) for c in codes))

    def test_every_value_is_a_valid_choice_and_fits_the_columns(self):
        kinds, natures, statements = ({k for k, _ in c} for c in (Account.KINDS, Account.NATURES, Account.STATEMENTS))
        for code, name, kind, nature, statement, description, is_group in CHART_ROWS:
            self.assertIn(kind, kinds, code)
            self.assertIn(nature, natures, code)
            self.assertIn(statement, statements, code)
            self.assertTrue(name.strip() and len(name) <= 150, code)
            self.assertLessEqual(len(description), 255, code)
            self.assertIsInstance(is_group, bool)

    def test_counts_per_class_and_statement(self):
        counts = {}
        for code, _n, _k, _na, statement, _d, _g in CHART_ROWS:
            klass = DIGIT_CLASS[code[0]]
            counts[klass] = counts.get(klass, 0) + 1
            self.assertEqual(statement, "balance_sheet" if klass in ("asset", "liability", "equity") else "income_statement", code)
        self.assertEqual(counts, {"asset": 64, "liability": 18, "equity": 4, "income": 10, "expense": 36})

    def test_kind_agrees_with_the_first_digit_of_the_code(self):
        for code, _n, kind, *_rest in CHART_ROWS:
            self.assertEqual(broad_type(kind, code), DIGIT_CLASS[code[0]], code)

    def test_contra_accounts_keep_the_nature_given_in_the_guide(self):
        credit_assets = sorted(r[0] for r in CHART_ROWS if r[0][0] == "1" and r[3] == "credit")
        self.assertEqual(credit_assets, ["112170", "112210", "112310", "112410", "112510"])
        self.assertEqual([r[3] for r in CHART_ROWS if r[0] == "330000"], ["debit"])

    def test_group_accounts(self):
        groups = {r[0] for r in CHART_ROWS if r[6]}
        self.assertEqual(len(groups), 22)
        self.assertTrue({"100000", "200000", "300000", "400000", "500000", "212000", "213000"} <= groups)
        self.assertEqual({r[0] for r in CHART_ROWS if r[2] == "view"}, {"100000", "200000", "400000", "500000"})
        for code in groups:
            self.assertTrue(any(suggest_parent(other, GROUPS) == code for other in GROUPS), f"{code} بدون أبناء")

    def test_default_role_accounts_exist_and_accept_entries(self):
        self.assertEqual(set(DEFAULT_ROLE_CODES), {role for role, _ in AccountMapping.ROLES})
        for role, code in DEFAULT_ROLE_CODES.items():
            self.assertIn(code, GROUPS, role)
            self.assertFalse(GROUPS[code], role)

    def test_hierarchy_has_five_roots_and_no_loops(self):
        parents = {code: suggest_parent(code, GROUPS) for code in GROUPS}
        self.assertEqual(sorted(c for c, p in parents.items() if p is None),
                         ["100000", "200000", "300000", "400000", "500000"])
        for code in GROUPS:
            depth, current = 0, code
            while parents[current]:
                current = parents[current]
                depth += 1
                self.assertLess(depth, 7, code)

    def test_suggest_parent_examples(self):
        for code, parent in (("111110", "111100"), ("112210", "112200"), ("141100", "140000"), ("141400", "140000"),
                             ("151100", "150000"), ("121100", "120000"), ("212200", "212000"), ("511100", "510000"),
                             ("110000", "100000"), ("100000", None)):
            self.assertEqual(suggest_parent(code, GROUPS), parent, code)

    def test_five_digit_rule_is_optional_for_custom_accounts(self):
        self.assertEqual(suggest_parent("111110", GROUPS, five_digit_rule=False), "110000")
        self.assertEqual(suggest_parent("141450", GROUPS), "141400")
        self.assertEqual(suggest_parent("141450", GROUPS, five_digit_rule=False), "140000")


# ============================== أدوات مشتركة ==============================
class ChartBase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="شركة دليل", code="CHT")
        self.wh = Warehouse.objects.create(company=self.company, code="M", name="رئيسي")
        self.supplier = Partner.objects.create(company=self.company, name="مورد", kind="supplier")
        self.customer = Partner.objects.create(company=self.company, name="عميل", kind="customer")
        self.prod = Product.objects.create(company=self.company, code="P1", name="صنف", cost=Decimal("60"))

    def acc(self, code, company=None):
        return Account.objects.get(company=company or self.company, code=code)

    def receive_purchase(self, number="PO-1", qty=10, cost=40):
        order = PurchaseOrder.objects.create(company=self.company, number=number, supplier=self.supplier)
        PurchaseLine.objects.create(order=order, product=self.prod, qty=qty, cost=cost)
        receive_order(order, self.wh)
        return order

    def sale_order(self, number="SO-1", qty=2, price=100):
        order = SalesOrder.objects.create(company=self.company, number=number, customer=self.customer)
        SalesLine.objects.create(order=order, product=self.prod, qty=qty, price=price)
        return order

    def entry_lines(self, journal, reference):
        entry = JournalEntry.objects.get(company=self.company, journal__code=journal, reference=reference)
        return {l.account.code: (l.debit, l.credit) for l in entry.lines.select_related("account")}


# ============================== التحميل والترقية ==============================
class LoadChartTests(ChartBase):
    def test_load_creates_the_whole_chart_with_parents_types_and_groups(self):
        self.assertEqual(load_default_chart(self.company), 132)
        self.assertEqual(Account.objects.filter(company=self.company).count(), 132)
        self.assertEqual(self.acc("111110").parent.code, "111100")
        self.assertEqual(self.acc("141400").parent.code, "140000")
        self.assertIsNone(self.acc("100000").parent)
        self.assertEqual([self.acc(c).type for c in ("151000", "211000", "330000", "411000", "511000")],
                         ["asset", "liability", "equity", "income", "expense"])
        self.assertEqual((self.acc("330000").nature, self.acc("112170").nature), ("debit", "credit"))
        self.assertEqual(Account.objects.filter(company=self.company, is_group=True).count(), 22)
        self.assertTrue(self.acc("110000").is_group and not self.acc("151000").is_group)

    def test_second_load_adds_nothing(self):
        load_default_chart(self.company)
        self.assertEqual(load_default_chart(self.company), 0)
        self.assertEqual(Account.objects.filter(company=self.company).count(), 132)

    def test_load_keeps_user_edits_and_does_not_touch_other_companies(self):
        other = Company.objects.create(name="شركة تانية", code="OTH")
        load_default_chart(self.company)
        Account.objects.filter(company=self.company, code="151000").update(name="الخزينة الرئيسية")
        load_default_chart(self.company)
        self.assertEqual(self.acc("151000").name, "الخزينة الرئيسية")
        self.assertEqual(Account.objects.filter(company=other).count(), 0)

    def test_load_restores_a_deleted_account(self):
        load_default_chart(self.company)
        Account.objects.filter(company=self.company, code="151300").delete()
        self.assertEqual(load_default_chart(self.company), 1)
        self.assertEqual(self.acc("151300").parent.code, "150000")

    def test_ensure_chart_loads_the_chart_and_journals_only_the_first_time(self):
        ensure_chart(self.company)
        self.assertEqual(Account.objects.filter(company=self.company).count(), 132)
        self.assertEqual(Journal.objects.filter(company=self.company).count(), 3)
        Account.objects.filter(company=self.company, code="151300").delete()
        ensure_chart(self.company)
        self.assertFalse(Account.objects.filter(company=self.company, code="151300").exists())


class LegacyUpgradeTests(ChartBase):
    def make_legacy(self):
        legacy = {}
        for old, (name, _new) in LEGACY_CHART.items():
            legacy[old] = Account.objects.create(company=self.company, code=old, name=name,
                                                 type=broad_type("", old))
        return legacy

    def test_old_entries_move_to_the_new_accounts_and_old_accounts_go(self):
        legacy = self.make_legacy()
        journal = Journal.objects.create(company=self.company, code="SAL", name="مبيعات")
        entry = JournalEntry.objects.create(company=self.company, journal=journal, reference="OLD-1", memo="قديم")
        JournalLine.objects.create(entry=entry, account=legacy["1300"], debit=Decimal("50"))
        JournalLine.objects.create(entry=entry, account=legacy["2100"], credit=Decimal("50"))
        ensure_chart(self.company)
        self.assertFalse(Account.objects.filter(company=self.company, code__in=list(LEGACY_CHART)).exists())
        self.assertEqual(Account.objects.filter(company=self.company).count(), 132)
        self.assertEqual(sorted(l.account.code for l in entry.lines.all()), ["121000", "211000"])
        rows, debit, credit = trial_balance(self.company)
        self.assertEqual((debit, credit), (Decimal("50"), Decimal("50")))

    def test_a_custom_account_with_a_legacy_code_is_left_alone(self):
        Account.objects.create(company=self.company, code="1200", name="حساب خاص بالمستخدم", type="asset")
        ensure_chart(self.company)
        self.assertEqual(self.acc("1200").name, "حساب خاص بالمستخدم")

    def test_upgrade_is_safe_to_run_again(self):
        self.make_legacy()
        ensure_chart(self.company)
        self.assertEqual(upgrade_legacy_accounts(self.company), 0)


# ============================== الحسابات الافتراضية ==============================
class RolesTests(ChartBase):
    def setUp(self):
        super().setUp()
        ensure_chart(self.company)

    def test_default_codes_are_used_without_a_mapping(self):
        for role, code in DEFAULT_ROLE_CODES.items():
            self.assertEqual(account_for(self.company, role).code, code)

    def test_a_mapping_overrides_the_default(self):
        custom = Account.objects.create(company=self.company, code="411100", name="مبيعات جملة", type="income")
        AccountMapping.objects.create(company=self.company, role="sales", account=custom)
        self.assertEqual(account_for(self.company, "sales"), custom)

    def test_missing_account_gives_a_clear_error(self):
        Account.objects.filter(company=self.company, code="141000").delete()
        with self.assertRaisesMessage(ValueError, "حساب العملاء"):
            account_for(self.company, "receivable")

    def test_role_usage_follows_the_mapping(self):
        self.assertEqual(role_usage(self.acc("141000")), ["حساب العملاء"])
        custom = Account.objects.create(company=self.company, code="141900", name="عملاء خاص", type="asset")
        AccountMapping.objects.create(company=self.company, role="receivable", account=custom)
        self.assertEqual(role_usage(self.acc("141000")), [])
        self.assertEqual(role_usage(custom), ["حساب العملاء"])

    def test_postings_follow_a_remapped_role(self):
        custom = Account.objects.create(company=self.company, code="411100", name="مبيعات جملة", type="income")
        AccountMapping.objects.create(company=self.company, role="sales", account=custom)
        post_sale(self.sale_order())
        lines = self.entry_lines("SAL", "SO-1")
        self.assertEqual(lines["411100"], (Decimal("0"), Decimal("200")))
        self.assertNotIn("411000", lines)


# ============================== القيود ==============================
class PostingTests(ChartBase):
    def test_sale_posts_to_receivable_sales_vat_cogs_and_inventory(self):
        post_sale(self.sale_order())  # 2 × 100 = 200 + 14% = 228، والتكلفة 2 × 60 = 120
        self.assertEqual(self.entry_lines("SAL", "SO-1"), {
            "141000": (Decimal("228"), Decimal("0")), "411000": (Decimal("0"), Decimal("200")),
            "212200": (Decimal("0"), Decimal("28")), "511000": (Decimal("120"), Decimal("0")),
            "121000": (Decimal("0"), Decimal("120")),
        })

    def test_cash_and_bank_payments_use_their_own_accounts(self):
        order = self.receive_purchase()
        cash = pay_order(order, Decimal("100"), method="cash")
        bank = pay_order(order, Decimal("50"), method="bank")
        self.assertEqual(self.entry_lines("PAY", f"PO-1-P{cash.pk}"),
                         {"211000": (Decimal("100"), Decimal("0")), "151000": (Decimal("0"), Decimal("100"))})
        self.assertEqual(self.entry_lines("PAY", f"PO-1-P{bank.pk}"),
                         {"211000": (Decimal("50"), Decimal("0")), "151100": (Decimal("0"), Decimal("50"))})

    def test_group_accounts_cannot_receive_entries(self):
        ensure_chart(self.company)
        with self.assertRaisesMessage(ValueError, "تجميعي"):
            _post(self.company, "SAL", "X-1", "تجربة", [(self.acc("120000"), 10, 0), ("sales", 0, 10)])
        self.assertEqual(JournalEntry.objects.filter(company=self.company).count(), 0)

    def test_inactive_accounts_cannot_receive_entries(self):
        ensure_chart(self.company)
        Account.objects.filter(company=self.company, code="411000").update(is_active=False)
        with self.assertRaisesMessage(ValueError, "موقوف"):
            post_sale(self.sale_order())
        self.assertEqual(JournalEntry.objects.filter(company=self.company).count(), 0)

    def test_an_account_of_another_company_is_refused(self):
        other = Company.objects.create(name="شركة تانية", code="OTH")
        ensure_chart(other)
        ensure_chart(self.company)
        with self.assertRaisesMessage(ValueError, "مش تبع الشركة"):
            _post(self.company, "SAL", "X-2", "تجربة", [(self.acc("411000", other), 10, 0), ("sales", 0, 10)])

    def test_unbalanced_entries_are_refused(self):
        ensure_chart(self.company)
        with self.assertRaisesMessage(ValueError, "مش متوازن"):
            _post(self.company, "SAL", "X-3", "تجربة", [("receivable", 10, 0), ("sales", 0, 9)])


# ============================== الأرصدة وميزان المراجعة ==============================
class BalancesTests(ChartBase):
    def test_balances_roll_up_to_the_parents(self):
        self.receive_purchase()  # مخزون 400 + ضريبة مدخلات 56 = موردين 456
        net = account_balances(self.company)
        for code, expected in (("121000", 400), ("120000", 400), ("141400", 56), ("140000", 56), ("100000", 456),
                               ("211000", -456), ("210000", -456), ("200000", -456)):
            self.assertEqual(net[self.acc(code).pk], Decimal(expected), code)
        self.assertEqual(balance_for_display(self.acc("211000"), net[self.acc("211000").pk]), Decimal("456"))
        self.assertEqual(balance_for_display(self.acc("100000"), net[self.acc("100000").pk]), Decimal("456"))

    def test_trial_balance_hides_empty_accounts_unless_asked(self):
        self.receive_purchase()
        rows, debit, credit = trial_balance(self.company)
        self.assertEqual(sorted(r["account"].code for r in rows), ["121000", "141400", "211000"])
        self.assertEqual((debit, credit), (Decimal("456"), Decimal("456")))
        all_rows, d2, c2 = trial_balance(self.company, include_zero=True)
        self.assertEqual((len(all_rows), d2, c2), (132, Decimal("456"), Decimal("456")))


# ============================== قواعد الحذف ==============================
class DeleteRulesTests(ChartBase):
    def setUp(self):
        super().setUp()
        ensure_chart(self.company)

    def test_a_free_custom_account_can_be_deleted(self):
        custom = Account.objects.create(company=self.company, code="191000", name="حر", type="asset")
        self.assertEqual(delete_blockers(custom), [])

    def test_default_role_account_is_protected_even_without_entries(self):
        reasons = delete_blockers(self.acc("141000"))
        self.assertEqual(len(reasons), 1)
        self.assertIn("حساب العملاء", reasons[0])

    def test_account_with_entries_or_children_is_protected(self):
        self.receive_purchase()
        self.assertTrue(any("قيود" in r for r in delete_blockers(self.acc("121000"))))
        self.assertTrue(any("فرعية" in r for r in delete_blockers(self.acc("120000"))))

    def test_account_is_free_again_after_the_role_moves_elsewhere(self):
        custom = Account.objects.create(company=self.company, code="141900", name="عملاء خاص", type="asset")
        AccountMapping.objects.create(company=self.company, role="receivable", account=custom)
        self.assertEqual(delete_blockers(self.acc("141000")), [])


# ============================== استيراد وتصدير ==============================
class ImportExportTests(ChartBase):
    def setUp(self):
        super().setUp()
        ensure_chart(self.company)

    def rows(self, text):
        return list(csv.reader(io.StringIO(text)))

    def test_export_has_a_header_and_every_account_in_tree_order(self):
        rows = self.rows(export_csv(self.company))
        self.assertEqual(rows[0], ["code", "name", "kind", "nature", "statement", "parent_code", "is_group",
                                   "is_active", "description"])
        self.assertEqual(len(rows), 133)
        self.assertEqual(rows[1][0], "100000")
        by_code = {r[0]: r for r in rows[1:]}
        self.assertEqual((by_code["111110"][5], by_code["110000"][6], by_code["151000"][6]), ("111100", "1", "0"))

    def test_export_then_import_rebuilds_the_chart_in_a_new_company(self):
        other = Company.objects.create(name="شركة تانية", code="OTH")
        self.assertEqual(import_csv(other, export_csv(self.company)), (132, 0, []))
        self.assertEqual(Account.objects.filter(company=other).count(), 132)
        self.assertEqual(self.acc("111110", other).parent.code, "111100")
        self.assertEqual((self.acc("112170", other).nature, self.acc("330000", other).type), ("credit", "equity"))
        self.assertEqual(Account.objects.filter(company=other, is_group=True).count(), 22)

    def test_import_updates_existing_accounts_by_code(self):
        rows = self.rows(export_csv(self.company))
        for row in rows:
            if row[0] == "151000":
                row[1] = "الخزينة الرئيسية"
        buffer = io.StringIO()
        csv.writer(buffer).writerows(rows)
        self.assertEqual(import_csv(self.company, buffer.getvalue()), (0, 132, []))
        self.assertEqual(self.acc("151000").name, "الخزينة الرئيسية")

    def test_import_accepts_arabic_labels_bom_and_minimal_columns(self):
        text = "\ufeffcode,name,kind,nature,statement\n191000,حساب تجريبي,أصول ثابتة,مدين,المركز المالي\n"
        self.assertEqual(import_csv(self.company, text), (1, 0, []))
        account = self.acc("191000")
        self.assertEqual((account.kind, account.nature, account.statement, account.type),
                         ("fixed_asset", "debit", "balance_sheet", "asset"))
        self.assertEqual(account.parent.code, "100000")
        self.assertEqual(import_csv(self.company, "code,name\n192000,بالحد الأدنى\n"), (1, 0, []))
        minimal = self.acc("192000")
        self.assertEqual((minimal.kind, minimal.nature, minimal.statement, minimal.is_active),
                         ("current_asset", "debit", "balance_sheet", True))

    def test_bad_files_are_rejected_and_nothing_is_saved(self):
        before = Account.objects.filter(company=self.company).count()
        bad_files = {
            "code,name\n12ab,اسم\n": "الكود",
            "code,name\n193000,\n": "الاسم",
            "code,name,kind\n193000,اسم,نوع_مش_موجود\n": "نوع الحساب",
            "code,name,nature\n193000,اسم,يمين\n": "الطبيعة",
            "code,name\n193000,أول\n193000,تاني\n": "مكرر",
            "code,name,parent_code\n193000,اسم,999999\n": "غير موجود",
            "code,name,parent_code\n193000,اسم,193000\n": "هو نفس الحساب",
            "code,name,parent_code\n193000,أ,194000\n194000,ب,193000\n": "دورة",
            "code,name,is_group\n193000,اسم,ممكن\n": "صح/خطأ",
            "code,name\n194000,سليم\n19x000,بايظ\n": "الكود",
            "name\nاسم بدون كود\n": "code",
        }
        for text, expected in bad_files.items():
            created, updated, errors = import_csv(self.company, text)
            self.assertEqual((created, updated), (0, 0), text)
            self.assertTrue(any(expected in e for e in errors), (text, errors))
        self.assertEqual(Account.objects.filter(company=self.company).count(), before)

    def test_protected_changes_are_rejected(self):
        self.receive_purchase()
        _c, _u, errors = import_csv(self.company, "code,name,is_group\n121000,المخزون,1\n")
        self.assertTrue(any("عليه قيود" in e for e in errors))
        _c, _u, errors = import_csv(self.company, "code,name,is_active\n141000,العملاء,0\n")
        self.assertTrue(any("حساب افتراضي" in e for e in errors))

    def test_row_limit(self):
        with mock.patch("accounting.chart.MAX_IMPORT_ROWS", 2):
            _c, _u, errors = import_csv(self.company, "code,name\n195000,أ\n196000,ب\n197000,ج\n")
        self.assertTrue(any("أكبر من" in e for e in errors))


# ============================== الفورم ==============================
class AccountFormTests(ChartBase):
    def setUp(self):
        super().setUp()
        ensure_chart(self.company)

    def form(self, instance=None, company=None, **data):
        company = company or self.company
        payload = {"code": "141450", "name": "عملاء تجزئة", "kind": "receivable", "parent": "", "nature": "debit",
                   "statement": "balance_sheet", "is_active": "on", "description": ""}
        payload.update(data)
        return AccountForm(payload, instance=instance or Account(company=company), company=company)

    def test_new_account_gets_a_derived_type_and_a_suggested_parent(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        account = form.save()
        self.assertEqual((account.type, account.parent.code), ("asset", "140000"))
        payable = self.form(code="211500", kind="payable", nature="credit").save()
        self.assertEqual((payable.type, payable.parent.code), ("liability", "210000"))

    def test_an_explicit_parent_is_respected(self):
        form = self.form(parent=self.acc("141000").pk)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().parent.code, "141000")

    def test_code_rules(self):
        for bad in ("14ab50", "12", "12345678901", ""):
            self.assertIn("code", self.form(code=bad).errors, bad)
        self.assertIn("code", self.form(code="141000").errors)  # موجود قبل كده
        other = Company.objects.create(name="شركة تانية", code="OTH")
        self.assertTrue(self.form(company=other, code="141000").is_valid())

    def test_parent_cannot_be_itself_or_a_descendant(self):
        account = self.acc("110000")
        form = AccountForm(instance=account, company=self.company)
        allowed = set(form.fields["parent"].queryset.values_list("code", flat=True))
        self.assertFalse(allowed & {"110000", "111100", "111110", "112100"})
        self.assertIn("100000", allowed)
        bad = self.form(instance=account, code="110000", name=account.name, kind="fixed_asset",
                        parent=self.acc("111110").pk)
        self.assertIn("parent", bad.errors)

    def test_account_with_entries_keeps_its_code_and_cannot_become_a_group(self):
        self.receive_purchase()
        inventory = self.acc("121000")
        self.assertIn("code", self.form(instance=inventory, code="121999", name=inventory.name,
                                        kind="current_asset").errors)
        self.assertIn("is_group", self.form(instance=inventory, code="121000", name=inventory.name,
                                            kind="current_asset", is_group="on").errors)

    def test_default_role_accounts_cannot_be_stopped_or_turned_into_groups(self):
        receivable = self.acc("141000")
        base = dict(code="141000", name=receivable.name, kind="receivable")
        self.assertIn("is_active", self.form(instance=receivable, is_active="", **base).errors)
        self.assertIn("is_group", self.form(instance=receivable, is_group="on", **base).errors)

    def test_a_normal_account_can_be_stopped_and_its_type_follows_the_kind(self):
        account = self.form(code="191000", kind="fixed_asset").save()
        form = self.form(instance=account, code="191000", kind="payable", nature="credit", is_active="")
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual((saved.type, saved.is_active), ("liability", False))


# ============================== الشاشات ==============================
class ChartViewTests(ChartBase):
    def setUp(self):
        super().setUp()
        SeedModules().handle()
        CompanyModule.objects.update_or_create(company=self.company, module=Module.objects.get(code="accounting"),
                                               defaults={"enabled": True})
        User = get_user_model()
        self.boss = User.objects.create_user(username="boss", password="x", company=self.company,
                                             is_company_manager=True)
        self.clerk = User.objects.create_user(username="clerk", password="x", company=self.company)
        self.clerk.allowed_modules.set([Module.objects.get(code="accounting")])
        self.nobody = User.objects.create_user(username="nobody", password="x", company=self.company)
        self.client.force_login(self.boss)

    def msgs(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]

    def custom(self, code="191000", name="حساب تجريبي", **extra):
        values = dict(type="asset", kind="current_asset")
        values.update(extra)
        return Account.objects.create(company=self.company, code=code, name=name, **values)

    def account_data(self, **extra):
        data = {"code": "141450", "name": "عملاء تجزئة", "kind": "receivable", "parent": "", "nature": "debit",
                "statement": "balance_sheet", "is_active": "on", "description": ""}
        data.update(extra)
        return data

    # ----- القايمة -----
    def test_first_visit_loads_the_default_chart(self):
        self.assertEqual(Account.objects.filter(company=self.company).count(), 0)
        response = self.client.get("/accounting/accounts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Account.objects.filter(company=self.company).count(), 132)
        self.assertEqual(len(response.context["rows"]), 132)

    def test_list_is_a_tree_with_indentation_and_group_rows(self):
        response = self.client.get("/accounting/accounts/")
        rows = {r["cells"][0]: r for r in response.context["rows"]}
        self.assertEqual(response.context["rows"][0]["cells"][0], "100000")
        self.assertTrue(rows["111110"]["cells"][1].startswith("\u00a0" * 12))
        self.assertTrue(rows["110000"]["group"] and not rows["151000"]["group"])
        self.assertEqual(rows["151000"]["cells"][5], "—")

    def test_list_shows_rolled_up_balances(self):
        self.receive_purchase()
        rows = {r["cells"][0]: r for r in self.client.get("/accounting/accounts/").context["rows"]}
        self.assertEqual((rows["121000"]["cells"][5], rows["100000"]["cells"][5], rows["211000"]["cells"][5]),
                         (Decimal("400"), Decimal("456"), Decimal("456")))

    def test_list_filter_and_search(self):
        self.assertEqual(len(self.client.get("/accounting/accounts/?f=asset").context["rows"]), 64)
        self.assertEqual(len(self.client.get("/accounting/accounts/?f=expense").context["rows"]), 36)
        codes = [r["cells"][0] for r in self.client.get("/accounting/accounts/?q=151000").context["rows"]]
        self.assertEqual(codes, ["151000"])
        by_name = [r["cells"][0] for r in self.client.get("/accounting/accounts/?q=ضريبة القيمة").context["rows"]]
        self.assertIn("141400", by_name)

    def test_buttons_depend_on_the_role(self):
        response = self.client.get("/accounting/accounts/")
        self.assertEqual([url for _label, url in response.context["creates"]],
                         ["account_create", "account_import", "account_export"])
        self.assertEqual(len(response.context["post_actions"]), 1)
        self.client.force_login(self.clerk)
        response = self.client.get("/accounting/accounts/")
        self.assertEqual([url for _label, url in response.context["creates"]], ["account_export"])
        self.assertEqual(response.context["post_actions"], [])

    # ----- الصلاحيات -----
    def test_user_without_accounting_access_gets_403(self):
        ensure_chart(self.company)
        account = self.acc("151000")
        self.client.force_login(self.nobody)
        for path in ("/accounting/accounts/", f"/accounting/accounts/{account.pk}/", "/accounting/accounts/new/",
                     f"/accounting/accounts/{account.pk}/edit/", "/accounting/accounts/roles/",
                     "/accounting/accounts/import/", "/accounting/accounts/export/", "/accounting/trial-balance/"):
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_clerk_can_read_but_not_change_the_chart(self):
        ensure_chart(self.company)
        account = self.acc("151000")
        self.client.force_login(self.clerk)
        for path in ("/accounting/accounts/", f"/accounting/accounts/{account.pk}/", "/accounting/accounts/export/",
                     "/accounting/trial-balance/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        for path in ("/accounting/accounts/new/", f"/accounting/accounts/{account.pk}/edit/",
                     "/accounting/accounts/roles/", "/accounting/accounts/import/"):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        for path in (f"/accounting/accounts/{account.pk}/toggle/", f"/accounting/accounts/{account.pk}/delete/",
                     "/accounting/accounts/load-default/"):
            self.assertEqual(self.client.post(path).status_code, 403, path)
        account.refresh_from_db()
        self.assertTrue(account.is_active)

    def test_post_only_endpoints_reject_get(self):
        account = self.custom()
        for path in (f"/accounting/accounts/{account.pk}/toggle/", f"/accounting/accounts/{account.pk}/delete/",
                     "/accounting/accounts/load-default/"):
            self.assertEqual(self.client.get(path).status_code, 405, path)

    def test_other_company_accounts_are_not_reachable(self):
        other = Company.objects.create(name="شركة تانية", code="OTH")
        ensure_chart(other)
        foreign = self.acc("151000", other)
        for path in (f"/accounting/accounts/{foreign.pk}/", f"/accounting/accounts/{foreign.pk}/edit/"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        for action in ("toggle", "delete"):
            self.assertEqual(self.client.post(f"/accounting/accounts/{foreign.pk}/{action}/").status_code, 404, action)
        self.assertTrue(Account.objects.filter(pk=foreign.pk, is_active=True).exists())

    # ----- التفاصيل -----
    def test_detail_shows_fields_balance_movements_and_actions(self):
        self.receive_purchase()
        account = self.acc("211000")
        response = self.client.get(f"/accounting/accounts/{account.pk}/")
        self.assertEqual(response.status_code, 200)
        fields = dict(response.context["fields"])
        self.assertEqual((fields["الكود"], fields["الحساب الرئيسي"], fields["حساب افتراضي لـ"]),
                         ("211000", "210000 الالتزامات الجارية (Current Liabilities)", "حساب الموردين"))
        self.assertEqual((fields["إجمالي الدائن"], fields["الرصيد"]), (Decimal("456"), Decimal("456")))
        self.assertEqual(len(response.context["tables"][0]["rows"]), 1)
        self.assertEqual([a["url"] for a in response.context["actions"]], ["account_toggle", "account_delete"])
        self.assertEqual(response.context["edit_url"], "account_edit")

    def test_detail_of_a_group_and_the_clerk_view(self):
        ensure_chart(self.company)
        group = self.acc("110000")
        fields = dict(self.client.get(f"/accounting/accounts/{group.pk}/").context["fields"])
        self.assertEqual(fields["يقبل قيود"], "لا (تجميعي)")
        self.client.force_login(self.clerk)
        response = self.client.get(f"/accounting/accounts/{group.pk}/")
        self.assertEqual((response.context["actions"], response.context["edit_url"]), ([], None))

    # ----- إنشاء وتعديل -----
    def test_create_account(self):
        ensure_chart(self.company)
        response = self.client.post("/accounting/accounts/new/", self.account_data())
        account = self.acc("141450")
        self.assertRedirects(response, f"/accounting/accounts/{account.pk}/", fetch_redirect_response=False)
        self.assertEqual((account.type, account.parent.code), ("asset", "140000"))
        self.assertEqual(self.client.get("/accounting/accounts/new/").status_code, 200)

    def test_invalid_account_is_not_saved(self):
        ensure_chart(self.company)
        before = Account.objects.filter(company=self.company).count()
        for data in (self.account_data(code="abc"), self.account_data(code="141000")):
            self.assertEqual(self.client.post("/accounting/accounts/new/", data).status_code, 200)
        self.assertEqual(Account.objects.filter(company=self.company).count(), before)

    def test_edit_account(self):
        account = self.custom()
        self.assertEqual(self.client.get(f"/accounting/accounts/{account.pk}/edit/").status_code, 200)
        data = self.account_data(code="191000", name="اسم جديد", kind="fixed_asset")
        response = self.client.post(f"/accounting/accounts/{account.pk}/edit/", data)
        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        self.assertEqual((account.name, account.kind, account.type), ("اسم جديد", "fixed_asset", "asset"))

    # ----- إيقاف ومسح -----
    def test_toggle_stops_and_reactivates_but_refuses_default_accounts(self):
        account = self.custom()
        self.client.post(f"/accounting/accounts/{account.pk}/toggle/")
        account.refresh_from_db()
        self.assertFalse(account.is_active)
        self.client.post(f"/accounting/accounts/{account.pk}/toggle/")
        account.refresh_from_db()
        self.assertTrue(account.is_active)
        ensure_chart(self.company)
        receivable = self.acc("141000")
        response = self.client.post(f"/accounting/accounts/{receivable.pk}/toggle/")
        receivable.refresh_from_db()
        self.assertTrue(receivable.is_active)
        self.assertTrue(any("حساب افتراضي" in m for m in self.msgs(response)))

    def test_delete_free_account_but_protect_the_rest(self):
        free = self.custom()
        response = self.client.post(f"/accounting/accounts/{free.pk}/delete/")
        self.assertRedirects(response, "/accounting/accounts/", fetch_redirect_response=False)
        self.assertFalse(Account.objects.filter(pk=free.pk).exists())
        self.receive_purchase()
        for code, word in (("121000", "قيود"), ("120000", "فرعية"), ("141000", "حساب افتراضي")):
            account = self.acc(code)
            response = self.client.post(f"/accounting/accounts/{account.pk}/delete/")
            self.assertTrue(Account.objects.filter(pk=account.pk).exists(), code)
            self.assertTrue(any(word in m for m in self.msgs(response)), code)

    def test_load_default_adds_the_missing_accounts(self):
        ensure_chart(self.company)
        Account.objects.filter(company=self.company, code="151300").delete()
        response = self.client.post("/accounting/accounts/load-default/")
        self.assertRedirects(response, "/accounting/accounts/", fetch_redirect_response=False)
        self.assertTrue(Account.objects.filter(company=self.company, code="151300").exists())
        self.assertTrue(any("1 حساب" in m for m in self.msgs(response)))

    # ----- الحسابات الافتراضية -----
    def test_roles_screen_shows_and_saves_the_mapping(self):
        response = self.client.get("/accounting/accounts/roles/")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(set(form.fields), {role for role, _ in AccountMapping.ROLES})
        self.assertEqual(form.fields["sales"].initial, self.acc("411000").pk)
        custom = self.custom("411100", "مبيعات جملة", type="income", kind="income", nature="credit")
        data = {role: account_for(self.company, role).pk for role, _ in AccountMapping.ROLES}
        data["sales"] = custom.pk
        self.assertRedirects(self.client.post("/accounting/accounts/roles/", data), "/accounting/accounts/roles/",
                             fetch_redirect_response=False)
        self.assertEqual(account_for(self.company, "sales"), custom)
        self.assertEqual(AccountMapping.objects.filter(company=self.company).count(), 9)
        post_sale(self.sale_order())
        self.assertIn("411100", self.entry_lines("SAL", "SO-1"))

    def test_roles_screen_refuses_group_and_inactive_accounts(self):
        ensure_chart(self.company)
        stopped = self.custom("191000", "موقوف", is_active=False)
        for bad in (self.acc("120000"), stopped):
            data = {role: account_for(self.company, role).pk for role, _ in AccountMapping.ROLES}
            data["inventory"] = bad.pk
            response = self.client.post("/accounting/accounts/roles/", data)
            self.assertEqual(response.status_code, 200)
            self.assertIn("inventory", response.context["form"].errors)
        self.assertEqual(AccountMapping.objects.filter(company=self.company).count(), 0)

    # ----- التصدير والاستيراد -----
    def test_export_download(self):
        for user in (self.boss, self.clerk):
            self.client.force_login(user)
            response = self.client.get("/accounting/accounts/export/")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response["Content-Type"].startswith("text/csv"))
            self.assertIn("attachment", response["Content-Disposition"])
            body = response.content
            self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(len(body.decode("utf-8-sig").strip().splitlines()), 133)

    def upload(self, text=None, raw=None):
        data = raw if raw is not None else text.encode("utf-8")
        return self.client.post("/accounting/accounts/import/",
                                {"file": SimpleUploadedFile("chart.csv", data, content_type="text/csv")})

    def test_import_screen(self):
        ensure_chart(self.company)
        self.assertEqual(self.client.get("/accounting/accounts/import/").status_code, 200)
        response = self.upload("code,name,kind\n195000,حساب مستورد,fixed_asset\n")
        self.assertRedirects(response, "/accounting/accounts/", fetch_redirect_response=False)
        self.assertEqual(self.acc("195000").kind, "fixed_asset")

    def test_import_errors_are_listed_and_nothing_changes(self):
        ensure_chart(self.company)
        before = Account.objects.filter(company=self.company).count()
        response = self.upload("code,name\n195000,سليم\nxx,بايظ\n")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("الكود" in e for e in response.context["form"].non_field_errors()))
        self.assertEqual(Account.objects.filter(company=self.company).count(), before)

    def test_import_rejects_files_that_are_not_utf8(self):
        response = self.upload(raw="code,name\n195000,اسم\n".encode("utf-16"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)

    # ----- ميزان المراجعة -----
    def test_trial_balance_screen(self):
        self.receive_purchase()
        response = self.client.get("/accounting/trial-balance/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((len(response.context["rows"]), response.context["balanced"]), (3, True))
        everything = self.client.get("/accounting/trial-balance/?all=1")
        self.assertEqual((len(everything.context["rows"]), everything.context["show_all"]), (132, True))


# ============================== أمر load_chart ==============================
class LoadChartCommandTests(ChartBase):
    def run_command(self, *args):
        out = io.StringIO()
        call_command("load_chart", *args, stdout=out)
        return out.getvalue()

    def test_loads_one_company_or_all(self):
        other = Company.objects.create(name="شركة تانية", code="OTH")
        self.assertIn("132", self.run_command("--company", "CHT"))
        self.assertEqual(Account.objects.filter(company=self.company).count(), 132)
        self.assertEqual(Account.objects.filter(company=other).count(), 0)
        self.run_command("--all")
        self.assertEqual(Account.objects.filter(company=other).count(), 132)

    def test_requires_a_company_and_rejects_unknown_codes(self):
        with self.assertRaises(CommandError):
            self.run_command()
        with self.assertRaises(CommandError):
            self.run_command("--company", "NOPE")

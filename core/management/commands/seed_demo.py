from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from accounts.models import User  # noqa
from core.models import Company, CompanyModule, Module, Partner
from core.services import set_module
from inventory.models import Product, Warehouse
from inventory.services import receive

DEMO_PASSWORD = "Demo@1234"  # للتجربة المحلية فقط


class Command(BaseCommand):
    help = "شركة تجريبية (ALNOOR) بمستخدمين ومخزن وأصناف"

    def handle(self, *args, **options):
        call_command("seed_modules", verbosity=0)
        call_command("seed_chart_of_accounts", verbosity=0)
        User = get_user_model()
        company, _ = Company.objects.get_or_create(code="ALNOOR", defaults={"name": "شركة النور للتجارة"})

        # كل المديولات مفعّلة (الرئيسية والفرعية) عشان تشوف الشكل الكامل
        for module in Module.objects.all():
            CompanyModule.objects.update_or_create(company=company, module=module, defaults={"enabled": True})

        manager, _ = User.objects.get_or_create(username="ahmed", defaults={
            "first_name": "أحمد", "company": company, "is_company_manager": True})
        manager.set_password(DEMO_PASSWORD); manager.company = company; manager.is_company_manager = True; manager.save()

        # حساب الدخول المؤقت: admin / steven (لازم يتغير قبل أي استخدام حقيقي)
        admin_user, _ = User.objects.get_or_create(username="admin", defaults={"first_name": "المدير"})
        admin_user.set_password("steven")
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_user.company = company
        admin_user.is_company_manager = True
        admin_user.save()

        omar, _ = User.objects.get_or_create(username="omar", defaults={"first_name": "عمر", "company": company})
        omar.set_password(DEMO_PASSWORD); omar.company = company; omar.save()
        omar.allowed_modules.set(Module.objects.filter(code__in=["inventory", "barcode"]))

        main_wh, _ = Warehouse.objects.get_or_create(company=company, code="MAIN", defaults={"name": "المخزن الرئيسي"})

        Partner.objects.get_or_create(company=company, name="مؤسسة الأمل", defaults={"kind": "customer", "city": "القاهرة"})
        Partner.objects.get_or_create(company=company, name="مصنع الشرق", defaults={"kind": "supplier", "city": "الجيزة"})

        products = [("CEM-50", "أسمنت 50 كجم", Decimal("150")), ("STL-12", "حديد تسليح 12 مم", Decimal("42000")),
                    ("PNT-20", "دهان داخلي 20 لتر", Decimal("1450"))]
        for code, name, price in products:
            prod, _ = Product.objects.get_or_create(company=company, code=code,
                                                    defaults={"name": name, "sale_price": price})
            if not prod.stock_moves.exists():
                receive(company=company, product=prod, warehouse=main_wh, qty=Decimal("100"), reference="رصيد افتتاحي")

        self.stdout.write(self.style.SUCCESS("تم تجهيز بيانات التجربة. admin / steven ، وباقي الحسابات: " + DEMO_PASSWORD))

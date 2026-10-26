import os
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from core.models import Company, CompanyModule, Module, Partner
from inventory.models import Product, Warehouse
from inventory.services import receive

DEMO_PASSWORD = "Demo@1234"  # للتجربة المحلية فقط (غيّره بـ VEYRA_DEMO_PASSWORD)


class Command(BaseCommand):
    help = "شركة تجريبية (ALNOOR) بمستخدمين ومخزن وأصناف بباركود. للتجربة المحلية فقط."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true",
                            help="تشغيل بيانات التجربة حتى لو VEYRA_DEBUG=0 (مش للإنتاج)")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("seed_demo للتجربة المحلية بس ومعاه حسابات بكلمة مرور معروفة. "
                               "لو متأكد استخدم --force.")
        password = os.environ.get("VEYRA_DEMO_PASSWORD", DEMO_PASSWORD)
        call_command("seed_modules", verbosity=0)
        User = get_user_model()
        company, _ = Company.objects.get_or_create(code="ALNOOR", defaults={"name": "شركة النور للتجارة"})

        # كل المديولات مفعّلة (الرئيسية والفرعية) عشان تشوف الشكل الكامل
        for module in Module.objects.all():
            CompanyModule.objects.update_or_create(company=company, module=module, defaults={"enabled": True})

        manager, _ = User.objects.get_or_create(username="ahmed", defaults={
            "first_name": "أحمد", "company": company, "is_company_manager": True})
        manager.set_password(password)
        manager.company = company
        manager.is_company_manager = True
        manager.save()

        omar, _ = User.objects.get_or_create(username="omar", defaults={"first_name": "عمر", "company": company})
        omar.set_password(password)
        omar.company = company
        omar.save()
        omar.allowed_modules.set(Module.objects.filter(code__in=["inventory", "barcode"]))

        main_wh, _ = Warehouse.objects.get_or_create(company=company, code="MAIN", defaults={"name": "المخزن الرئيسي"})

        Partner.objects.get_or_create(company=company, name="مؤسسة الأمل", defaults={"kind": "customer", "city": "القاهرة"})
        Partner.objects.get_or_create(company=company, name="مصنع الشرق", defaults={"kind": "supplier", "city": "الجيزة"})

        # (الكود، الاسم، سعر البيع، التكلفة، الباركود)
        products = [
            ("CEM-50", "أسمنت 50 كجم", Decimal("150"), Decimal("120"), "6221000000011"),
            ("STL-12", "حديد تسليح 12 مم", Decimal("42000"), Decimal("38000"), "6221000000028"),
            ("PNT-20", "دهان داخلي 20 لتر", Decimal("1450"), Decimal("1100"), "6221000000035"),
        ]
        for code, name, price, cost, barcode in products:
            prod, _ = Product.objects.get_or_create(
                company=company, code=code,
                defaults={"name": name, "sale_price": price, "cost": cost, "barcode": barcode})
            if not prod.barcode:
                prod.barcode = barcode
                prod.save(update_fields=["barcode", "updated_at"])
            if not prod.stock_moves.exists():
                receive(company=company, product=prod, warehouse=main_wh, qty=Decimal("100"), reference="رصيد افتتاحي")

        self.stdout.write(self.style.SUCCESS(
            f"تم تجهيز بيانات التجربة. الحسابات: ahmed (مدير الشركة) و omar (مخزون بس) بكلمة المرور: {password}"))
        self.stdout.write("لحساب مالك النظام (لوحة الإدارة): python manage.py seed_owner")

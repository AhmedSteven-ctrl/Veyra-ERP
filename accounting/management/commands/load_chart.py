from django.core.management.base import BaseCommand, CommandError

from accounting.chart import load_default_chart, upgrade_legacy_accounts
from accounting.services import ensure_chart
from core.models import Company


class Command(BaseCommand):
    help = "يحمّل دليل الحسابات الافتراضي (نمط Odoo) لشركة أو لكل الشركات، ويرحّل الدليل القديم (4 أرقام) لو موجود"

    def add_arguments(self, parser):
        parser.add_argument("--company", help="كود الشركة")
        parser.add_argument("--all", action="store_true", help="كل الشركات")

    def handle(self, *args, **options):
        if options["all"]:
            companies = list(Company.objects.all())
        elif options["company"]:
            companies = list(Company.objects.filter(code=options["company"]))
            if not companies:
                raise CommandError(f"مفيش شركة بالكود {options['company']}")
        else:
            raise CommandError("حدد --company كود_الشركة أو --all")
        for company in companies:
            created = load_default_chart(company)
            moved = upgrade_legacy_accounts(company)
            ensure_chart(company)  # اليوميات (والدليل لو ناقص)
            self.stdout.write(f"{company.code}: {created} حساب جديد"
                              + (f"، ونقل {moved} حركة من الحسابات القديمة" if moved else ""))

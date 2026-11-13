from django.core.management.base import BaseCommand, CommandError

from core.models import Company, CompanyModule, Module


class Command(BaseCommand):
    help = "يفعّل كل المديولات (الرئيسية والفرعية) لشركة معينة، ويعطي مدير الشركة كل الصلاحيات"

    def add_arguments(self, parser):
        parser.add_argument("--company", default="ALNOOR", help="كود الشركة (الافتراضي ALNOOR)")
        parser.add_argument("--user", default="ahmed", help="اسم المستخدم اللي هيبقى مدير (الافتراضي ahmed). لو عايز حساب admin يدخل التطبيق: --user admin")

    def handle(self, *args, **opts):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            company = Company.objects.get(code=opts["company"])
        except Company.DoesNotExist:
            raise CommandError(f"الشركة {opts['company']} مش موجودة. شغّل seed_demo الأول")
        count = 0
        for module in Module.objects.all():
            CompanyModule.objects.update_or_create(company=company, module=module, defaults={"enabled": True})
            count += 1
        try:
            user = User.objects.get(username=opts["user"])
            user.company = company
            user.is_company_manager = True
            user.save(update_fields=["company", "is_company_manager"])
        except User.DoesNotExist:
            raise CommandError(f"المستخدم {opts['user']} مش موجود")
        self.stdout.write(self.style.SUCCESS(
            f"تم تفعيل {count} مديول لشركة {company.name}، والمستخدم {user.username} بقى مدير بكل الصلاحيات"))

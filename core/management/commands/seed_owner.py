from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "ينشئ حساب مالك النظام (admin) بصلاحيات كاملة على لوحة الإدارة"

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True})
        user.is_staff = True
        user.is_superuser = True
        user.set_password("admin")
        user.save()
        self.stdout.write(self.style.WARNING(
            "تحذير: كلمة المرور admin للتجربة المحلية بس. لازم تتغير قبل أي نشر أو عميل حقيقي."))
        self.stdout.write(self.style.SUCCESS("حساب admin جاهز على http://127.0.0.1:8000/admin/"))

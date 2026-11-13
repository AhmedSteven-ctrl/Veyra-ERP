import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.crypto import get_random_string


class Command(BaseCommand):
    help = "ينشئ حساب مالك النظام (admin) بصلاحيات كاملة على لوحة الإدارة، بكلمة مرور عشوائية تظهر مرة واحدة"

    def add_arguments(self, parser):
        parser.add_argument("--password", help="كلمة المرور. لو متحددتش (أو VEYRA_OWNER_PASSWORD) بتتولّد عشوائي")
        parser.add_argument("--reset", action="store_true", help="يعيد تعيين كلمة مرور admin لو موجود بالفعل")

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True})
        user.is_staff = True
        user.is_superuser = True
        if not (created or options["reset"]):
            user.save()
            self.stdout.write(self.style.WARNING("حساب admin موجود بالفعل وكلمة المرور ما اتغيرتش (استخدم --reset لو عايز تغيّرها)."))
            return
        supplied = options["password"] or os.environ.get("VEYRA_OWNER_PASSWORD")
        password = supplied or get_random_string(16)
        user.set_password(password)
        user.must_change_password = not supplied  # الباسورد المتولّد لازم يتغيّر أول دخول
        user.save()
        self.stdout.write(self.style.SUCCESS("حساب admin جاهز على http://127.0.0.1:8000/admin/"))
        if not supplied:
            self.stdout.write(self.style.WARNING(f"كلمة المرور (بتظهر مرة واحدة، احفظها دلوقتي): {password}"))
            self.stdout.write("هيطلب منك تغييرها أول دخول.")

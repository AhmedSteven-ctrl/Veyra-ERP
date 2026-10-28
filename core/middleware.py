from django.shortcuts import redirect


DEFAULT_ADMIN_PASSWORD = "steven"


class ForcePasswordChange:
    """لو الحساب لسه بالباسورد الافتراضي (admin/admin) يتحول لشاشة تغيير الباسورد قبل أي شاشة تانية."""

    ALLOWED = ("/accounts/password/", "/accounts/logout/", "/admin/logout/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.username == "admin" and user.check_password(DEFAULT_ADMIN_PASSWORD):
            if not request.path.startswith(self.ALLOWED):
                return redirect("password_change")
        return self.get_response(request)

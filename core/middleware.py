from django.shortcuts import redirect


class ForcePasswordChange:
    """أي حساب عليه علامة "لازم يغيّر كلمة المرور" (بيتحط عليه لما كلمة السر تتولّد تلقائي)
    بيتحوّل لشاشة تغيير كلمة المرور قبل أي شاشة تانية."""

    ALLOWED = ("/accounts/password/", "/accounts/logout/", "/admin/logout/", "/static/", "/i18n/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and getattr(user, "must_change_password", False):
            if not request.path.startswith(self.ALLOWED):
                return redirect("password_change")
        return self.get_response(request)

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def module_required(code):
    """يمنع الدخول لأي شاشة مديول إلا لو المستخدم مسموحله بيه."""
    def deco(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.can_access(code):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return deco

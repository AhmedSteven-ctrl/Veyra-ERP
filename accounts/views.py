from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import CalendarForm, PreferencesForm, PrivateForm
from .models import UserProfile

TABS = [("prefs", "التفضيلات"), ("calendar", "التقويم"), ("private", "خاص"), ("security", "الأمان")]


@login_required
def my_preferences(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    tab = request.GET.get("tab", "prefs")
    form = None
    if request.method == "POST":
        ptab = request.POST.get("tab", "prefs")
        if ptab == "prefs":
            form = PreferencesForm(request.POST, instance=profile)
        elif ptab == "calendar":
            form = CalendarForm(request.POST, instance=profile)
        elif ptab == "private":
            form = PrivateForm(request.POST, instance=profile)
        if form and form.is_valid():
            form.save()
            messages.success(request, "تم حفظ التفضيلات")
            return redirect(f"/accounts/me/?tab={ptab}")
        tab = ptab
    if form is None:
        if tab == "calendar":
            form = CalendarForm(instance=profile)
        elif tab == "private":
            form = PrivateForm(instance=profile)
        else:
            form = PreferencesForm(instance=profile)
    sessions_count = sum(1 for s in Session.objects.filter(expire_date__gte=timezone.now())
                         if str(s.get_decoded().get("_auth_user_id")) == str(request.user.id))
    return render(request, "account_prefs.html", {
        "tabs": TABS, "tab": tab, "form": form, "profile": profile, "sessions_count": sessions_count,
    })


@login_required
@require_POST
def logout_all_devices(request):
    for s in Session.objects.filter(expire_date__gte=timezone.now()):
        if str(s.get_decoded().get("_auth_user_id")) == str(request.user.id):
            s.delete()
    messages.success(request, "تم تسجيل الخروج من كل الأجهزة. هتحتاج تدخل تاني.")
    return redirect("login")

from django.shortcuts import render

from core.decorators import module_required
from core.views import _list_page

from .models import JournalEntry
from .services import trial_balance


@module_required("accounting")
def journal_list(request):
    entries = JournalEntry.objects.filter(company=request.user.company).select_related("journal")
    rows = [{"id": e.id, "s": "posted", "detail": None,
             "cells": [e.reference, e.journal.name, e.memo, e.created_at.strftime("%Y-%m-%d")]} for e in entries]
    return _list_page(request, code="accounting", title="القيود اليومية", rows=rows,
                      columns=["المرجع", "اليومية", "البيان", "التاريخ"], statuses=[("posted", "مرحّل")])


@module_required("accounting")
def trial_balance_view(request):
    rows, total_d, total_c = trial_balance(request.user.company)
    return render(request, "trial_balance.html", {
        "rows": rows, "total_d": total_d, "total_c": total_c,
        "balanced": total_d == total_c, "menus": [("القيود اليومية", "journal_list"), ("ميزان المراجعة", "trial_balance")],
        "icon": "📊", "title": "ميزان المراجعة",
    })

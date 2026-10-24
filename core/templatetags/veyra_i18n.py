from django import template
from django.utils.translation import get_language

from core.i18n_dict import translate

register = template.Library()


@register.filter
def tr(value):
    """يترجم النص للإنجليزي لو اللغة الحالية en، وإلا بيرجعه زي ما هو."""
    if value is None:
        return ""
    return translate(str(value), get_language())

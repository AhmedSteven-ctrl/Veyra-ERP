from django.core.management.base import BaseCommand

from core.catalog import MODULES
from core.models import Module


class Command(BaseCommand):
    help = "يحمّل كتالوج المديولات (الرئيسية والفرعية) والاعتمادات بينها"

    def handle(self, *args, **options):
        objs = {}
        for order, (code, name, cat, parent, _deps) in enumerate(MODULES):
            obj, _ = Module.objects.update_or_create(
                code=code, defaults={"name": name, "category": cat, "sort": order})
            objs[code] = obj
        for code, name, cat, parent, _deps in MODULES:
            objs[code].parent = objs[parent] if parent else None
            objs[code].save(update_fields=["parent"])
        for code, _name, _cat, _parent, deps in MODULES:
            objs[code].depends_on.set([objs[d] for d in deps])
        self.stdout.write(self.style.SUCCESS(f"تم تحميل {len(objs)} مديول"))

"""قراءة ملف .env ورابط قاعدة البيانات (DATABASE_URL) من غير مكتبات خارجية."""
from urllib.parse import parse_qsl, unquote, urlparse


def load_env_file(path, environ):
    """يقرا KEY=VALUE من ملف .env ويضيفها لـ environ. متغيرات البيئة الموجودة فعلاً بتفضل أقوى من الملف."""
    try:
        with open(path, encoding="utf-8-sig") as handle:  # utf-8-sig بيشيل علامة BOM اللي Notepad وPowerShell بيضيفوها
            text = handle.read()
    except FileNotFoundError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            environ.setdefault(key, value)


def parse_database_url(url):
    """يحوّل رابط PostgreSQL (زي اللي بتنسخه من Neon) لإعدادات DATABASES في Django.
    بيقبل كمان الرابط لو اتنسخ كأمر كامل: psql '...'. رسائل الخطأ مش بتعرض الرابط عشان كلمة السر."""
    url = (url or "").strip()
    if url.startswith("psql"):
        url = url[len("psql"):].strip()
    url = url.strip("'\"")
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ValueError("الرابط لازم يبدأ بـ postgresql://")
    name = unquote(parsed.path.lstrip("/"))
    if not parsed.hostname or not name:
        raise ValueError("الرابط ناقص اسم السيرفر أو اسم القاعدة")
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port) if parsed.port else "",
        "OPTIONS": dict(parse_qsl(parsed.query)),  # sslmode وchannel_binding وغيرهم بيتبعتوا للسيرفر كما هم
        "CONN_HEALTH_CHECKS": True,
    }
    if "-pooler" in parsed.hostname:  # رابط الـ pooler (PgBouncer) مش بيدعم الـ server-side cursors
        config["DISABLE_SERVER_SIDE_CURSORS"] = True
    return config

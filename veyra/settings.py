import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
_DEV_KEY = "dev-only-change-me"
SECRET_KEY = os.environ.get("VEYRA_SECRET_KEY", _DEV_KEY)
DEBUG = os.environ.get("VEYRA_DEBUG", "1") == "1"
if not DEBUG and (SECRET_KEY == _DEV_KEY or SECRET_KEY.startswith("change-me")):
    raise ImproperlyConfigured("حدد VEYRA_SECRET_KEY قيمة طويلة عشوائية قبل التشغيل بـ VEYRA_DEBUG=0")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("VEYRA_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("VEYRA_CSRF_ORIGINS", "").split(",") if o.strip()]

# وراء HTTPS (Nginx أو Caddy): VEYRA_HTTPS=1 يفعّل الكوكيز الآمنة والتحويل لـ HTTPS
if os.environ.get("VEYRA_HTTPS") == "1":
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "accounts",
    "inventory",
    "accounting",
    "sales",
    "purchasing",
]

try:
    import whitenoise  # noqa: F401
    WHITENOISE_OK = True
except ImportError:
    WHITENOISE_OK = False

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    *(["whitenoise.middleware.WhiteNoiseMiddleware"] if WHITENOISE_OK else []),
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.ForcePasswordChange",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "veyra.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "core.context_processors.module_nav",
    ]},
}]

WSGI_APPLICATION = "veyra.wsgi.application"

# قاعدة البيانات: SQLite للتجربة على Windows، PostgreSQL للإنتاج
if os.environ.get("VEYRA_DB") == "postgres":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PG_NAME", "veyra"),
        "USER": os.environ.get("PG_USER", "veyra"),
        "PASSWORD": os.environ.get("PG_PASSWORD", ""),
        "HOST": os.environ.get("PG_HOST", "localhost"),
        "PORT": os.environ.get("PG_PORT", "5432"),
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "ar"
LANGUAGES = [("ar", "العربية"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

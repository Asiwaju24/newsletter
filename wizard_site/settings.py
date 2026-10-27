"""
Django settings for the newsletter platform.

All deployment-specific values come from environment variables (or a local
``.env`` file). See ``.env.example`` for the full list.
"""
import os
import sys
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

# --- Core security ----------------------------------------------------------

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or TESTING:
        SECRET_KEY = "insecure-development-key-do-not-use-in-production"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is not set. Generate one with: "
            "python -c 'from django.core.management.utils import get_random_secret_key as g; print(g())'"
        )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

if not DEBUG and not TESTING:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", 60 * 60 * 24 * 30))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # Only enable when a trusted reverse proxy (Render, Fly, nginx...) sets the header.
    if env_bool("DJANGO_BEHIND_PROXY", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Use the first X-Forwarded-For hop for rate limiting. Only enable behind a trusted proxy.
TRUST_X_FORWARDED_FOR = env_bool("DJANGO_TRUST_X_FORWARDED_FOR", False)

# --- Applications -----------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "newsletters",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "wizard_site.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "newsletters.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "wizard_site.wsgi.application"
ASGI_APPLICATION = "wizard_site.asgi.application"

# --- Database ---------------------------------------------------------------

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- Auth -------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

if TESTING:  # fast hashing keeps the test suite quick
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

# --- Internationalisation ---------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

# --- Static files -----------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

_static_backend = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if DEBUG or TESTING
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)
WHITENOISE_USE_FINDERS = DEBUG
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _static_backend},
}

# --- Email ------------------------------------------------------------------

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Dispatch <no-reply@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --- Newsletter platform ----------------------------------------------------

SITE_NAME = os.environ.get("SITE_NAME", "Dispatch")
# Absolute base URL used inside emails (confirmation / unsubscribe links).
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000").rstrip("/")
# True: "Send now" delivers inside the request (fine for development / tiny lists).
# False: issues are queued and delivered by `manage.py send_queued_issues`.
NEWSLETTER_SEND_INLINE = env_bool("NEWSLETTER_SEND_INLINE", DEBUG)
# An issue stuck in "sending" for longer than this is picked up again.
NEWSLETTER_STALE_SENDING_MINUTES = int(os.environ.get("NEWSLETTER_STALE_SENDING_MINUTES", 15))
# Subscribe form throttle, per IP address.
NEWSLETTER_SUBSCRIBE_LIMIT = int(os.environ.get("NEWSLETTER_SUBSCRIBE_LIMIT", 10))
NEWSLETTER_SUBSCRIBE_WINDOW_SECONDS = int(os.environ.get("NEWSLETTER_SUBSCRIBE_WINDOW_SECONDS", 3600))

# --- Logging ----------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}

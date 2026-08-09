from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "development-only-secret-key")
DEBUG = os.environ.get("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "ALLOWED_HOSTS",
        "127.0.0.1,localhost,.onrender.com",
    ).split(",")
    if host.strip()
]

RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
if RENDER_EXTERNAL_HOSTNAME:
    render_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)


def _register_custom_domains(domain_csv: str) -> None:
    """CUSTOM_DOMAIN veya sabit canlı domain → ALLOWED_HOSTS + CSRF."""
    for _domain in domain_csv.split(","):
        host = _domain.strip().lower()
        if not host:
            continue
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)
        if not host.startswith("."):
            https_origin = f"https://{host}"
            if https_origin not in CSRF_TRUSTED_ORIGINS:
                CSRF_TRUSTED_ORIGINS.append(https_origin)


_register_custom_domains(os.environ.get("CUSTOM_DOMAIN", ""))
# Render Environment boş olsa bile cinilisarayproje.com 400 vermesin
if not DEBUG:
    _register_custom_domains("cinilisarayproje.com,www.cinilisarayproje.com")

CANONICAL_HOST = os.environ.get("CANONICAL_HOST", "").strip().lower()
if not CANONICAL_HOST and not DEBUG:
    CANONICAL_HOST = "cinilisarayproje.com"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "takip",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "config.middleware.CanonicalHostMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [
            BASE_DIR / "templates",
        ],

        "APP_DIRS": True,

        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "takip.context_processors.panel_branding",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "tr-tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Geliştirmede kaynak static/ klasöründen doğrudan servis et;
        # Manifest + boş staticfiles tasarımı kırıyordu.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AI_ASSISTANT_ENABLED = os.environ.get("AI_ASSISTANT_ENABLED", "True").lower() == "true"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
AI_ASSISTANT_MODEL = os.environ.get("AI_ASSISTANT_MODEL", "gpt-4o-mini")
AI_KTT_ANALYSIS_ENABLED = os.environ.get("AI_KTT_ANALYSIS_ENABLED", "True").lower() == "true"
AI_KTT_ANALYSIS_MAX_TOKENS = int(os.environ.get("AI_KTT_ANALYSIS_MAX_TOKENS", "2200"))
AI_PLATFORM_ENABLED = os.environ.get("AI_PLATFORM_ENABLED", "True").lower() == "true"
AI_PLATFORM_MAX_TOKENS = int(os.environ.get("AI_PLATFORM_MAX_TOKENS", "2000"))
AI_CACHE_HOURS = int(os.environ.get("AI_CACHE_HOURS", "24"))

# —— Bildirim e-posta ——
# SMTP yoksa console backend ile DEBUG'ta mail içeriği terminale yazılır.
BILDIRIM_EMAIL_AKTIF = os.environ.get("BILDIRIM_EMAIL_AKTIF", "True").lower() == "true"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "").strip()
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "").strip()
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "False").lower() == "true"
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "noreply@cinili-saray.local",
)
PANEL_PUBLIC_URL = os.environ.get("PANEL_PUBLIC_URL", "").strip()
if not PANEL_PUBLIC_URL and not DEBUG:
    PANEL_PUBLIC_URL = "https://cinilisarayproje.com"

if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = os.environ.get(
        "EMAIL_BACKEND",
        "django.core.mail.backends.console.EmailBackend",
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "takip.pdf_utils": {
            "handlers": ["console"],
            "level": "WARNING" if DEBUG else "ERROR",
        },
    },
}

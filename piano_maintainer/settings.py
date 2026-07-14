"""
Django settings for piano_maintainer project.
"""

from importlib.util import find_spec
from pathlib import Path
from decouple import config, Csv
from django.core.exceptions import ImproperlyConfigured
import dj_database_url, os
from dotenv import load_dotenv
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from .monitoring import make_sentry_traces_sampler, sanitize_sentry_event

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)

SENTRY_DSN = config("SENTRY_DSN", default="")
SENTRY_ENABLED = config(
    "SENTRY_ENABLED",
    default=bool(SENTRY_DSN) and not DEBUG,
    cast=bool,
)
SENTRY_ENVIRONMENT = config(
    "SENTRY_ENVIRONMENT",
    default="development" if DEBUG else "production",
)
SENTRY_RELEASE = config(
    "SENTRY_RELEASE",
    default=os.getenv("RENDER_GIT_COMMIT", ""),
)
SENTRY_TRACES_SAMPLE_RATE = config(
    "SENTRY_TRACES_SAMPLE_RATE",
    default=0.0,
    cast=float,
)

if not 0.0 <= SENTRY_TRACES_SAMPLE_RATE <= 1.0:
    raise ImproperlyConfigured(
        "SENTRY_TRACES_SAMPLE_RATE must be between 0.0 and 1.0."
    )

if SENTRY_ENABLED:
    if not SENTRY_DSN:
        raise ImproperlyConfigured("SENTRY_ENABLED=True requires SENTRY_DSN.")
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        release=SENTRY_RELEASE or None,
        integrations=[DjangoIntegration()],
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sampler=make_sentry_traces_sampler(SENTRY_TRACES_SAMPLE_RATE),
        before_send=sanitize_sentry_event,
        before_send_transaction=sanitize_sentry_event,
    )

BACKUP_DATABASE_URL = config("BACKUP_DATABASE_URL", default="")
BACKUP_S3_ENDPOINT = config("BACKUP_S3_ENDPOINT", default="")
BACKUP_S3_REGION = config("BACKUP_S3_REGION", default="")
BACKUP_S3_BUCKET = config("BACKUP_S3_BUCKET", default="")
BACKUP_S3_ACCESS_KEY_ID = config("BACKUP_S3_ACCESS_KEY_ID", default="")
BACKUP_S3_SECRET_ACCESS_KEY = config("BACKUP_S3_SECRET_ACCESS_KEY", default="")
BACKUP_S3_PREFIX = config("BACKUP_S3_PREFIX", default="overtone")
BACKUP_OBJECT_LOCK_DAYS = config(
    "BACKUP_OBJECT_LOCK_DAYS",
    default=30,
    cast=int,
)

# Comma-separated in .env, e.g. ALLOWED_HOSTS=localhost,127.0.0.1,myapp.com
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=Csv()
)

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:8000",
    cast=Csv()
)

# APPLICATIONS
INSTALLED_APPS = [
    "piano_maintainer.admin.PlatformAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "anymail",
    "maintenance",
]

SUPABASE_S3_REQUIRED = config("SUPABASE_S3_REQUIRED", default=False, cast=bool)
SUPABASE_S3_ENV_KEYS = (
    "SUPABASE_S3_ACCESS_KEY_ID",
    "SUPABASE_S3_SECRET_ACCESS_KEY",
    "SUPABASE_S3_BUCKET",
    "SUPABASE_S3_ENDPOINT",
)
SUPABASE_S3_MISSING_KEYS = [key for key in SUPABASE_S3_ENV_KEYS if not os.getenv(key)]
SUPABASE_S3_BUCKET = os.getenv("SUPABASE_S3_BUCKET")
SUPABASE_S3_ENABLED = all(
    os.getenv(key)
    for key in SUPABASE_S3_ENV_KEYS
) and find_spec("storages") is not None

if SUPABASE_S3_REQUIRED and SUPABASE_S3_MISSING_KEYS:
    raise ImproperlyConfigured(
        "SUPABASE_S3_REQUIRED=True but these settings are missing: "
        + ", ".join(SUPABASE_S3_MISSING_KEYS)
    )

if SUPABASE_S3_REQUIRED and find_spec("storages") is None:
    raise ImproperlyConfigured(
        "SUPABASE_S3_REQUIRED=True but django-storages is not installed."
    )

if SUPABASE_S3_ENABLED:
    INSTALLED_APPS.append("storages")

STORAGES = {
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedStaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

if SUPABASE_S3_ENABLED:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": os.environ["SUPABASE_S3_ACCESS_KEY_ID"],
            "secret_key": os.environ["SUPABASE_S3_SECRET_ACCESS_KEY"],
            "bucket_name": os.environ["SUPABASE_S3_BUCKET"],
            "region_name": os.environ.get("SUPABASE_REGION", "us-east-1"),
            "endpoint_url": os.environ["SUPABASE_S3_ENDPOINT"],
            "addressing_style": "path",
            "signature_version": "s3v4",
            "file_overwrite": False,
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 3600,
        },
    }
else:
    STORAGES["default"] = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    }

AUTH_USER_MODEL = "maintenance.Technician"


# MIDDLEWARE
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "maintenance.middleware.ActiveCompanyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "piano_maintainer.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "maintenance.context_processors.active_company",
            ],
        },
    },
]

WSGI_APPLICATION = "piano_maintainer.wsgi.application"


# DATABASE
DATABASE_URL = config("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
DATABASE_CONN_MAX_AGE = config("DATABASE_CONN_MAX_AGE", default=600, cast=int)
DATABASE_SSL_REQUIRE = not DATABASE_URL.startswith("sqlite:") and config(
    "DATABASE_SSL_REQUIRE",
    default=not DEBUG and not DATABASE_URL.startswith("sqlite:"),
    cast=bool,
)

DATABASES = {
    "default": dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=DATABASE_CONN_MAX_AGE,
        ssl_require=DATABASE_SSL_REQUIRE,
    )
}


# PASSWORD VALIDATION
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# INTERNATIONALIZATION
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# STATIC FILES
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedStaticFilesStorage"
    if DEBUG
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)


# MEDIA FILES
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(config("MEDIA_ROOT", default=str(BASE_DIR / "media")))


# LOGIN / LOGOUT
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24
EMAIL_NOTIFICATIONS_ENABLED = config(
    "EMAIL_NOTIFICATIONS_ENABLED",
    default=False,
    cast=bool,
)
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=25, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=10, cast=int)
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default="noreply@pianomaintainer.local",
)
RESEND_API_KEY = config("RESEND_API_KEY", default="")
ANYMAIL = {
    "RESEND_API_KEY": RESEND_API_KEY,
    "REQUESTS_TIMEOUT": EMAIL_TIMEOUT,
}
PRIVATE_MEDIA_URL_TTL = config(
    "PRIVATE_MEDIA_URL_TTL",
    default=900,
    cast=int,
)


# SECURITY HEADERS
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

SECURE_SSL_REDIRECT = config(
    "SECURE_SSL_REDIRECT",
    default=not DEBUG,
    cast=bool,
)
SESSION_COOKIE_SECURE = config(
    "SESSION_COOKIE_SECURE",
    default=not DEBUG,
    cast=bool,
)
CSRF_COOKIE_SECURE = config(
    "CSRF_COOKIE_SECURE",
    default=not DEBUG,
    cast=bool,
)
SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS",
    default=31536000 if not DEBUG else 0,
    cast=int,
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=not DEBUG,
    cast=bool,
)
SECURE_HSTS_PRELOAD = config(
    "SECURE_HSTS_PRELOAD",
    default=not DEBUG,
    cast=bool,
)

if config("USE_X_FORWARDED_PROTO", default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

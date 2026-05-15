"""
Django settings for piano_maintainer project.
"""

from importlib.util import find_spec
from pathlib import Path
from decouple import config, Csv
import dj_database_url, os
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)

# Comma-separated in .env, e.g. ALLOWED_HOSTS=localhost,127.0.0.1,myapp.com
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1,.onrender.com",
    cast=Csv()
)
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
if ".onrender.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".onrender.com")

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:8000",
    cast=Csv()
)
if RENDER_EXTERNAL_HOSTNAME:
    render_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)

# APPLICATIONS
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "maintenance",
]

SUPABASE_S3_BUCKET = os.getenv("SUPABASE_S3_BUCKET")
SUPABASE_S3_ENABLED = all(
    os.getenv(key)
    for key in (
        "SUPABASE_S3_ACCESS_KEY_ID",
        "SUPABASE_S3_SECRET_ACCESS_KEY",
        "SUPABASE_S3_BUCKET",
        "SUPABASE_S3_ENDPOINT",
    )
) and find_spec("storages") is not None

if SUPABASE_S3_ENABLED:
    INSTALLED_APPS.append("storages")

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
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
DEMO_DATA_RESET_ON_DEPLOY = config("DEMO_DATA_RESET_ON_DEPLOY", default=False, cast=bool)
DEMO_AUTO_LOGIN = config(
    "DEMO_AUTO_LOGIN",
    default=DEMO_DATA_RESET_ON_DEPLOY,
    cast=bool,
)
DEMO_AUTO_LOGIN_USERNAME = config("DEMO_AUTO_LOGIN_USERNAME", default="demo-admin")


# MIDDLEWARE
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "maintenance.middleware.DemoAutoLoginMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "piano_maintainer.wsgi.application"


# DATABASE
DATABASE_URL = config("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
DATABASE_SSL_REQUIRE = config(
    "DB_SSL_REQUIRE",
    default=not DEBUG and not DATABASE_URL.startswith("sqlite"),
    cast=bool,
)

DATABASES = {
    "default": dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
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
)


# MEDIA FILES
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# LOGIN / LOGOUT
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"


# SECURITY HEADERS
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Enable these when serving over HTTPS in production:
# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
# SECURE_HSTS_SECONDS = 31536000
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

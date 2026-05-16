import os
from importlib.util import find_spec

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Report whether the current environment is shaped for local development or SaaS production."

    REQUIRED_PRODUCTION_SETTINGS = [
        "SECRET_KEY",
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
        "DEFAULT_FROM_EMAIL",
        "PRIVATE_MEDIA_URL_TTL",
    ]

    def handle(self, *args, **options):
        missing = []
        warnings = []

        for setting_name in self.REQUIRED_PRODUCTION_SETTINGS:
            value = getattr(settings, setting_name, None)
            if not value:
                missing.append(setting_name)

        email_backend = getattr(settings, "EMAIL_BACKEND", "")
        if email_backend == "django.core.mail.backends.console.EmailBackend":
            warnings.append("EMAIL_BACKEND is still using the console backend.")
        elif email_backend == "django.core.mail.backends.smtp.EmailBackend":
            if getattr(settings, "EMAIL_HOST", "") in ("", "localhost"):
                warnings.append("EMAIL_HOST is not configured for production SMTP email delivery.")
            if not getattr(settings, "EMAIL_PORT", None):
                warnings.append("EMAIL_PORT is not configured for SMTP email delivery.")
            if not getattr(settings, "EMAIL_USE_TLS", False) and not getattr(settings, "EMAIL_USE_SSL", False):
                warnings.append("SMTP email is not configured to use TLS or SSL.")
            if not getattr(settings, "EMAIL_HOST_USER", ""):
                warnings.append("EMAIL_HOST_USER is not configured for SMTP email delivery.")

        engine = connection.settings_dict.get("ENGINE", "")
        if engine.endswith("sqlite3"):
            warnings.append("Database engine is SQLite. Use Postgres for production.")

        storages = getattr(settings, "STORAGES", {})
        media_backend = storages.get("default", {}).get("BACKEND", "")
        if "storages" not in media_backend and "S3" not in media_backend:
            warnings.append("File storage is not using an object-storage backend.")
            s3_env_keys = (
                "SUPABASE_S3_ACCESS_KEY_ID",
                "SUPABASE_S3_SECRET_ACCESS_KEY",
                "SUPABASE_S3_BUCKET",
                "SUPABASE_S3_ENDPOINT",
            )
            if all(os.getenv(key) for key in s3_env_keys) and find_spec("storages") is None:
                warnings.append("Supabase S3 env vars are present, but django-storages is not installed.")
            elif any(os.getenv(key) for key in s3_env_keys):
                missing_s3_keys = [key for key in s3_env_keys if not os.getenv(key)]
                if missing_s3_keys:
                    warnings.append(f"Supabase S3 configuration is incomplete: {', '.join(missing_s3_keys)}.")

        static_backend = storages.get("staticfiles", {}).get("BACKEND", "")
        if "ManifestStaticFilesStorage" not in static_backend:
            warnings.append("Static files are not using manifest storage.")

        if settings.DEBUG:
            warnings.append("DEBUG is True.")

        if not getattr(settings, "SECURE_SSL_REDIRECT", False):
            warnings.append("SECURE_SSL_REDIRECT is not enabled.")
        if not getattr(settings, "SESSION_COOKIE_SECURE", False):
            warnings.append("SESSION_COOKIE_SECURE is not enabled.")
        if not getattr(settings, "CSRF_COOKIE_SECURE", False):
            warnings.append("CSRF_COOKIE_SECURE is not enabled.")
        if getattr(settings, "SECURE_HSTS_SECONDS", 0) <= 0:
            warnings.append("SECURE_HSTS_SECONDS is not enabled.")

        self.stdout.write("SaaS readiness report")
        self.stdout.write(f"DEBUG={settings.DEBUG}")
        self.stdout.write(f"Database engine={engine}")
        self.stdout.write(f"Email backend={email_backend}")
        self.stdout.write(f"Default file storage={media_backend or 'django default'}")
        self.stdout.write(f"Static file storage={static_backend or 'django default'}")
        self.stdout.write(f"SECURE_SSL_REDIRECT={settings.SECURE_SSL_REDIRECT}")
        self.stdout.write(f"SESSION_COOKIE_SECURE={settings.SESSION_COOKIE_SECURE}")
        self.stdout.write(f"CSRF_COOKIE_SECURE={settings.CSRF_COOKIE_SECURE}")
        self.stdout.write(f"SECURE_HSTS_SECONDS={settings.SECURE_HSTS_SECONDS}")

        if missing:
            self.stdout.write(self.style.WARNING("\nMissing production-oriented settings:"))
            for setting_name in missing:
                self.stdout.write(f" - {setting_name}")

        if warnings:
            self.stdout.write(self.style.WARNING("\nWarnings:"))
            for warning in warnings:
                self.stdout.write(f" - {warning}")

        if not missing and not warnings:
            self.stdout.write(self.style.SUCCESS("\nThis environment looks production-ready."))

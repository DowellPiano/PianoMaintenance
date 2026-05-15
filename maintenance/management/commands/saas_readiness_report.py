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

        engine = connection.settings_dict.get("ENGINE", "")
        if engine.endswith("sqlite3"):
            warnings.append("Database engine is SQLite. Use Postgres for production.")

        media_backend = getattr(settings, "DEFAULT_FILE_STORAGE", "")
        if "storages" not in media_backend and "S3" not in media_backend:
            warnings.append("File storage is not using an object-storage backend.")

        self.stdout.write("SaaS readiness report")
        self.stdout.write(f"DEBUG={settings.DEBUG}")
        self.stdout.write(f"Database engine={engine}")
        self.stdout.write(f"Email backend={email_backend}")
        self.stdout.write(f"Default file storage={media_backend or 'django default'}")

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

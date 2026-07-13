from django.core.management.base import BaseCommand, CommandError

from maintenance.backups import BackupError, perform_backup
from maintenance.jobs import tracked_job_run


class Command(BaseCommand):
    help = "Create, encrypt, lock, upload, and verify a PostgreSQL and media backup."

    def handle(self, *args, **options):
        try:
            with tracked_job_run("backup_to_b2") as job_run:
                result = perform_backup()
                job_run.result = result
        except BackupError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            "Backup completed and verified: " + result["daily_prefix"]
        ))
        if result["monthly_prefix"]:
            self.stdout.write(
                "Created monthly retention copy: " + result["monthly_prefix"]
            )
        self.stdout.write(
            f"Media files: {result['media_file_count']} | "
            f"Uploaded objects: {result['object_count']}"
        )

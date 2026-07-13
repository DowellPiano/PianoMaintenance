from pathlib import Path
import tempfile

from django.core.management.base import BaseCommand, CommandError

from maintenance.backups import BackupError, download_and_verify_backup
from maintenance.jobs import tracked_job_run


class Command(BaseCommand):
    help = "Download the latest (or specified) B2 backup and verify its checksums."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix",
            help="Exact backup prefix to verify; defaults to the latest daily backup.",
        )

    def handle(self, *args, **options):
        try:
            with tempfile.TemporaryDirectory(prefix="overtone-verify-") as directory:
                with tracked_job_run(
                    "verify_backup",
                    metadata={"requested_prefix": options.get("prefix") or "latest"},
                ) as job_run:
                    prefix, manifest = download_and_verify_backup(
                        Path(directory),
                        prefix=options.get("prefix"),
                    )
                    job_run.result = {
                        "prefix": prefix,
                        "created_at": manifest["created_at"],
                        "media_file_count": manifest["media_file_count"],
                    }
        except BackupError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            f"Backup downloaded and checksum-verified: {prefix}"
        ))

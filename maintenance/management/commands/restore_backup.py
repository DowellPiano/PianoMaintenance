import os
from pathlib import Path
import tempfile

from django.core.management.base import BaseCommand, CommandError

from maintenance.backups import (
    BackupError,
    download_and_verify_backup,
    extract_and_verify_media,
    restore_database_dump,
)


class Command(BaseCommand):
    help = "Restore a verified B2 backup into an explicitly isolated PostgreSQL database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix",
            help="Exact backup prefix to restore; defaults to the latest daily backup.",
        )
        parser.add_argument(
            "--media-output-dir",
            required=True,
            help="Empty local directory where restored media will be written.",
        )
        parser.add_argument(
            "--confirm-isolated-target",
            action="store_true",
            help="Required acknowledgement that RESTORE_DATABASE_URL is non-production.",
        )

    def handle(self, *args, **options):
        if not options["confirm_isolated_target"]:
            raise CommandError("Pass --confirm-isolated-target to run a restore.")
        target_database_url = os.getenv("RESTORE_DATABASE_URL", "").strip()
        if not target_database_url:
            raise CommandError(
                "Set RESTORE_DATABASE_URL to an isolated PostgreSQL database."
            )

        try:
            with tempfile.TemporaryDirectory(prefix="overtone-restore-") as directory:
                prefix, _manifest = download_and_verify_backup(
                    Path(directory),
                    prefix=options.get("prefix"),
                )
                restore_database_dump(
                    Path(directory) / "database.dump",
                    database_url=target_database_url,
                )
                media_count = extract_and_verify_media(
                    Path(directory) / "media.tar.gz",
                    options["media_output_dir"],
                )
        except BackupError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            f"Restored and verified {prefix}; media files restored: {media_count}."
        ))
        self.stdout.write(
            "Run Django migrations, check_tenant_integrity, and application smoke tests "
            "against RESTORE_DATABASE_URL before treating the drill as successful."
        )

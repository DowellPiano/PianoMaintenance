from datetime import datetime, timezone as datetime_timezone
from io import StringIO
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from .backups import (
    BackupConfig,
    BackupError,
    create_database_dump,
    create_media_archive,
    extract_and_verify_media,
    perform_backup,
)
from .models import JobRun


BACKUP_SETTINGS = {
    "BACKUP_S3_ENDPOINT": "s3.us-east-005.backblazeb2.com",
    "BACKUP_S3_REGION": "us-east-005",
    "BACKUP_S3_BUCKET": "overtone-backup-test",
    "BACKUP_S3_ACCESS_KEY_ID": "test-key-id",
    "BACKUP_S3_SECRET_ACCESS_KEY": "test-secret",
    "BACKUP_S3_PREFIX": "overtone",
    "BACKUP_OBJECT_LOCK_DAYS": 30,
}


class FakeBackupClient:
    def __init__(self, *, monthly_exists=False):
        self.monthly_exists = monthly_exists
        self.objects = {}

    def list_objects_v2(self, **kwargs):
        if self.monthly_exists:
            return {"Contents": [{"Key": f"{kwargs['Prefix']}old/manifest.json"}]}
        return {"Contents": []}

    def upload_file(self, filename, bucket, key, ExtraArgs):
        self.objects[key] = {
            "body": Path(filename).read_bytes(),
            "bucket": bucket,
            "extra_args": ExtraArgs,
        }

    def head_object(self, *, Bucket, Key):
        item = self.objects[Key]
        return {
            "ContentLength": len(item["body"]),
            "Metadata": item["extra_args"]["Metadata"],
            "ServerSideEncryption": item["extra_args"]["ServerSideEncryption"],
            "ObjectLockMode": item["extra_args"]["ObjectLockMode"],
        }


@override_settings(**BACKUP_SETTINGS)
class BackupConfigTests(SimpleTestCase):
    def test_endpoint_is_normalized_and_region_matches_endpoint(self):
        config = BackupConfig.from_settings()

        self.assertEqual(
            config.endpoint_url,
            "https://s3.us-east-005.backblazeb2.com",
        )
        self.assertEqual(config.region_name, "us-east-005")

    @override_settings(BACKUP_S3_REGION="us-east")
    def test_short_display_region_is_rejected(self):
        with self.assertRaisesMessage(BackupError, "us-east-005"):
            BackupConfig.from_settings()

    @override_settings(BACKUP_S3_BUCKET="OvertoneBackup")
    def test_uppercase_bucket_name_is_rejected(self):
        with self.assertRaisesMessage(BackupError, "lowercase"):
            BackupConfig.from_settings()

    @override_settings(BACKUP_S3_SECRET_ACCESS_KEY="")
    def test_missing_secret_is_rejected(self):
        with self.assertRaisesMessage(
            BackupError,
            "BACKUP_S3_SECRET_ACCESS_KEY",
        ):
            BackupConfig.from_settings()


class MediaArchiveTests(SimpleTestCase):
    def test_archive_and_restore_preserve_and_verify_media(self):
        with tempfile.TemporaryDirectory() as source_directory, tempfile.TemporaryDirectory() as work_directory:
            storage = FileSystemStorage(location=source_directory)
            storage.save("photos/26/07/12/piano.jpg", ContentFile(b"photo-data"))
            archive_path = Path(work_directory) / "media.tar.gz"
            restore_directory = Path(work_directory) / "restored"

            result = create_media_archive(archive_path, storage=storage)
            restored_count = extract_and_verify_media(
                archive_path,
                restore_directory,
            )

            self.assertEqual(result["file_count"], 1)
            self.assertEqual(restored_count, 1)
            self.assertEqual(
                (restore_directory / "photos/26/07/12/piano.jpg").read_bytes(),
                b"photo-data",
            )

    def test_restore_requires_an_empty_directory(self):
        with tempfile.TemporaryDirectory() as source_directory, tempfile.TemporaryDirectory() as work_directory:
            storage = FileSystemStorage(location=source_directory)
            storage.save("photo.jpg", ContentFile(b"photo-data"))
            archive_path = Path(work_directory) / "media.tar.gz"
            restore_directory = Path(work_directory) / "restored"
            restore_directory.mkdir()
            (restore_directory / "existing.txt").write_text("keep", encoding="utf-8")
            create_media_archive(archive_path, storage=storage)

            with self.assertRaisesMessage(BackupError, "must be empty"):
                extract_and_verify_media(archive_path, restore_directory)


@override_settings(**BACKUP_SETTINGS)
class BackupServiceTests(SimpleTestCase):
    @patch("maintenance.backups._run_postgres_command")
    def test_database_dump_is_limited_to_the_django_public_schema(self, mocked_run):
        database = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "overtone",
            "HOST": "localhost",
            "PORT": "5432",
            "USER": "test",
            "PASSWORD": "secret",
            "OPTIONS": {},
        }
        with patch("maintenance.backups._database_settings", return_value=database):
            with tempfile.TemporaryDirectory() as directory:
                create_database_dump(Path(directory) / "database.dump")

        command = mocked_run.call_args.args[0]
        self.assertIn("--schema=public", command)

    def test_backup_uploads_daily_and_first_monthly_copy_with_protection(self):
        client = FakeBackupClient()
        created_at = datetime(2026, 7, 12, 6, tzinfo=datetime_timezone.utc)

        with tempfile.TemporaryDirectory() as media_directory:
            storage = FileSystemStorage(location=media_directory)
            storage.save("photos/piano.jpg", ContentFile(b"photo-data"))

            def create_dump(path):
                Path(path).write_bytes(b"postgres-dump")

            with patch("maintenance.backups.build_backup_client", return_value=client), patch(
                "maintenance.backups.create_database_dump",
                side_effect=create_dump,
            ):
                result = perform_backup(storage=storage, created_at=created_at)

        self.assertEqual(result["media_file_count"], 1)
        self.assertIsNotNone(result["monthly_prefix"])
        self.assertEqual(result["object_count"], 6)
        self.assertEqual(len(client.objects), 6)
        for key, item in client.objects.items():
            self.assertTrue(key.startswith("overtone/"))
            self.assertEqual(item["bucket"], "overtone-backup-test")
            self.assertEqual(item["extra_args"]["ServerSideEncryption"], "AES256")
            self.assertEqual(item["extra_args"]["ObjectLockMode"], "GOVERNANCE")
            self.assertIn("sha256", item["extra_args"]["Metadata"])

    def test_existing_monthly_backup_is_not_duplicated(self):
        client = FakeBackupClient(monthly_exists=True)

        with tempfile.TemporaryDirectory() as media_directory:
            storage = FileSystemStorage(location=media_directory)

            def create_dump(path):
                Path(path).write_bytes(b"postgres-dump")

            with patch("maintenance.backups.build_backup_client", return_value=client), patch(
                "maintenance.backups.create_database_dump",
                side_effect=create_dump,
            ):
                result = perform_backup(storage=storage)

        self.assertIsNone(result["monthly_prefix"])
        self.assertEqual(result["object_count"], 3)


class BackupCommandTests(TestCase):
    @patch("maintenance.management.commands.backup_to_b2.perform_backup")
    def test_success_is_recorded_in_job_history(self, mocked_backup):
        mocked_backup.return_value = {
            "daily_prefix": "overtone/daily/backup",
            "monthly_prefix": None,
            "media_file_count": 2,
            "object_count": 3,
        }
        out = StringIO()

        call_command("backup_to_b2", stdout=out)

        job_run = JobRun.objects.get(job_name="backup_to_b2")
        self.assertEqual(job_run.status, JobRun.Status.SUCCESS)
        self.assertEqual(job_run.result["media_file_count"], 2)
        self.assertIn("completed and verified", out.getvalue())

    @patch(
        "maintenance.management.commands.backup_to_b2.perform_backup",
        side_effect=BackupError("B2 rejected the credentials"),
    )
    def test_failure_is_recorded_and_returns_command_error(self, mocked_backup):
        with self.assertRaisesMessage(CommandError, "rejected the credentials"):
            call_command("backup_to_b2")

        job_run = JobRun.objects.get(job_name="backup_to_b2")
        self.assertEqual(job_run.status, JobRun.Status.FAILED)
        self.assertIn("rejected the credentials", job_run.error_message)

    @patch("maintenance.management.commands.run_daily_operations.call_command")
    def test_daily_operations_runs_generation_even_if_backup_fails(self, mocked_call):
        def run(command_name, **kwargs):
            if command_name == "backup_to_b2":
                raise CommandError("backup failed")

        mocked_call.side_effect = run

        with self.assertRaisesMessage(CommandError, "backup_to_b2"):
            call_command("run_daily_operations")

        self.assertEqual(
            [call.args[0] for call in mocked_call.call_args_list],
            ["backup_to_b2", "generate_work_orders"],
        )


class RestoreCommandSafetyTests(SimpleTestCase):
    def test_confirmation_is_required_before_any_restore_work(self):
        with tempfile.TemporaryDirectory() as media_directory:
            with self.assertRaisesMessage(CommandError, "confirm-isolated-target"):
                call_command("restore_backup", "--media-output-dir", media_directory)

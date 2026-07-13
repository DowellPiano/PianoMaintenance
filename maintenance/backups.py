from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
from typing import BinaryIO
from urllib.parse import urlparse
from uuid import uuid4
import re

import boto3
from botocore.config import Config as BotoConfig
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
import dj_database_url


BACKUP_FORMAT_VERSION = 1
MEDIA_MANIFEST_NAME = "_overtone_media_manifest.json"


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupConfig:
    endpoint_url: str
    region_name: str
    bucket_name: str
    access_key_id: str
    secret_access_key: str
    prefix: str
    object_lock_days: int

    @classmethod
    def from_settings(cls):
        endpoint = settings.BACKUP_S3_ENDPOINT.strip()
        if endpoint and "://" not in endpoint:
            endpoint = f"https://{endpoint}"
        config = cls(
            endpoint_url=endpoint.rstrip("/"),
            region_name=settings.BACKUP_S3_REGION.strip(),
            bucket_name=settings.BACKUP_S3_BUCKET.strip(),
            access_key_id=settings.BACKUP_S3_ACCESS_KEY_ID.strip(),
            secret_access_key=settings.BACKUP_S3_SECRET_ACCESS_KEY.strip(),
            prefix=settings.BACKUP_S3_PREFIX.strip().strip("/"),
            object_lock_days=settings.BACKUP_OBJECT_LOCK_DAYS,
        )
        config.validate()
        return config

    def validate(self):
        required = {
            "BACKUP_S3_ENDPOINT": self.endpoint_url,
            "BACKUP_S3_REGION": self.region_name,
            "BACKUP_S3_BUCKET": self.bucket_name,
            "BACKUP_S3_ACCESS_KEY_ID": self.access_key_id,
            "BACKUP_S3_SECRET_ACCESS_KEY": self.secret_access_key,
            "BACKUP_S3_PREFIX": self.prefix,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise BackupError(
                "Backup configuration is incomplete: " + ", ".join(missing)
            )
        if not self.endpoint_url.startswith("https://"):
            raise BackupError("BACKUP_S3_ENDPOINT must use HTTPS.")
        if not re.fullmatch(
            r"(?=.{3,63}$)(?!\d+\.\d+\.\d+\.\d+$)[a-z0-9]"
            r"(?:[a-z0-9.-]*[a-z0-9])?",
            self.bucket_name,
        ) or ".." in self.bucket_name:
            raise BackupError(
                "BACKUP_S3_BUCKET must use a lowercase S3-compatible bucket name."
            )
        hostname = urlparse(self.endpoint_url).hostname or ""
        if hostname.startswith("s3.") and hostname.endswith(".backblazeb2.com"):
            endpoint_region = hostname[len("s3."):-len(".backblazeb2.com")]
            if self.region_name != endpoint_region:
                raise BackupError(
                    "BACKUP_S3_REGION must match the region in the Backblaze endpoint "
                    f"({endpoint_region})."
                )
        if not 1 <= self.object_lock_days <= 3000:
            raise BackupError("BACKUP_OBJECT_LOCK_DAYS must be between 1 and 3000.")


@dataclass(frozen=True)
class BackupFile:
    filename: str
    path: Path
    size: int
    sha256: str
    content_type: str


class _HashingReader:
    def __init__(self, raw: BinaryIO):
        self.raw = raw
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size=-1):
        chunk = self.raw.read(size)
        if chunk:
            self.digest.update(chunk)
            self.bytes_read += len(chunk)
        return chunk


def _sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_storage_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or name == MEDIA_MANIFEST_NAME:
        raise BackupError(f"Unsafe media object name cannot be archived: {name!r}")
    return path.as_posix()


def _iter_storage_files(storage, directory=""):
    try:
        directories, files = storage.listdir(directory)
    except (NotImplementedError, OSError) as exc:
        raise BackupError(
            "The configured media storage does not support recursive listing."
        ) from exc

    for filename in sorted(files):
        yield _safe_storage_name(
            str(PurePosixPath(directory) / filename) if directory else filename
        )
    for child in sorted(directories):
        child_directory = (
            str(PurePosixPath(directory) / child) if directory else child
        )
        yield from _iter_storage_files(storage, child_directory)


def create_media_archive(destination, *, storage=None, created_at=None):
    storage = storage or default_storage
    created_at = created_at or timezone.now()
    destination = Path(destination)
    entries = []

    with tarfile.open(destination, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name in _iter_storage_files(storage):
            size = storage.size(name)
            info = tarfile.TarInfo(name=name)
            info.size = size
            info.mode = 0o600
            info.mtime = int(created_at.timestamp())
            with storage.open(name, "rb") as source:
                hashing_source = _HashingReader(source)
                archive.addfile(info, hashing_source)
            if hashing_source.bytes_read != size:
                raise BackupError(
                    f"Media object changed while it was being archived: {name}"
                )
            entries.append({
                "name": name,
                "size": size,
                "sha256": hashing_source.digest.hexdigest(),
            })

        manifest_bytes = json.dumps(
            {
                "format_version": BACKUP_FORMAT_VERSION,
                "created_at": created_at.isoformat(),
                "files": entries,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        info = tarfile.TarInfo(name=MEDIA_MANIFEST_NAME)
        info.size = len(manifest_bytes)
        info.mode = 0o600
        info.mtime = int(created_at.timestamp())
        from io import BytesIO

        archive.addfile(info, BytesIO(manifest_bytes))

    return {
        "file_count": len(entries),
        "source_bytes": sum(entry["size"] for entry in entries),
    }


def _database_settings(database_url=None):
    database_url = database_url or settings.BACKUP_DATABASE_URL
    if database_url:
        return dj_database_url.parse(database_url, conn_max_age=0)
    return settings.DATABASES["default"]


def _postgres_command_env(database):
    env = os.environ.copy()
    if database.get("PASSWORD"):
        env["PGPASSWORD"] = database["PASSWORD"]
    sslmode = database.get("OPTIONS", {}).get("sslmode")
    if sslmode:
        env["PGSSLMODE"] = str(sslmode)
    return env


def _postgres_connection_args(database):
    engine = database.get("ENGINE", "")
    if "postgresql" not in engine:
        raise BackupError("Database backup and restore require PostgreSQL.")
    if not database.get("NAME"):
        raise BackupError("The PostgreSQL database name is missing.")

    args = []
    if database.get("HOST"):
        args.extend(["--host", str(database["HOST"])])
    if database.get("PORT"):
        args.extend(["--port", str(database["PORT"])])
    if database.get("USER"):
        args.extend(["--username", str(database["USER"])])
    args.extend(["--dbname", str(database["NAME"])])
    return args


def _run_postgres_command(command, *, database, error_label):
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=_postgres_command_env(database),
        )
    except FileNotFoundError as exc:
        raise BackupError(
            f"{command[0]} is not installed in this environment."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown error").strip()[-2000:]
        raise BackupError(f"{error_label}: {detail}") from exc


def create_database_dump(destination, *, database_url=None):
    database = _database_settings(database_url)
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--schema=public",
        "--file",
        str(destination),
        *_postgres_connection_args(database),
    ]
    _run_postgres_command(
        command,
        database=database,
        error_label="pg_dump failed",
    )


def restore_database_dump(source, *, database_url):
    target = _database_settings(database_url)
    production = settings.DATABASES["default"]
    target_identity = (
        target.get("HOST") or "localhost",
        str(target.get("PORT") or "5432"),
        target.get("NAME"),
    )
    production_identity = (
        production.get("HOST") or "localhost",
        str(production.get("PORT") or "5432"),
        production.get("NAME"),
    )
    if target_identity == production_identity:
        raise BackupError("Refusing to restore over the configured application database.")

    command = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        *_postgres_connection_args(target),
        str(source),
    ]
    _run_postgres_command(
        command,
        database=target,
        error_label="pg_restore failed",
    )


def build_backup_client(config):
    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        region_name=config.region_name,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def _upload_and_verify(client, config, backup_file, key, retain_until):
    client.upload_file(
        str(backup_file.path),
        config.bucket_name,
        key,
        ExtraArgs={
            "ContentType": backup_file.content_type,
            "Metadata": {"sha256": backup_file.sha256},
            "ServerSideEncryption": "AES256",
            "ObjectLockMode": "GOVERNANCE",
            "ObjectLockRetainUntilDate": retain_until,
        },
    )
    stored = client.head_object(Bucket=config.bucket_name, Key=key)
    if stored.get("ContentLength") != backup_file.size:
        raise BackupError(f"Uploaded backup size verification failed for {key}.")
    if stored.get("Metadata", {}).get("sha256") != backup_file.sha256:
        raise BackupError(f"Uploaded backup checksum metadata is missing for {key}.")
    if stored.get("ServerSideEncryption") != "AES256":
        raise BackupError(f"Uploaded backup is not encrypted at rest: {key}.")
    if stored.get("ObjectLockMode") != "GOVERNANCE":
        raise BackupError(f"Uploaded backup is not protected by Object Lock: {key}.")


def _prefix_has_complete_backup(client, config, prefix):
    response = client.list_objects_v2(
        Bucket=config.bucket_name,
        Prefix=f"{prefix.rstrip('/')}/",
        MaxKeys=1000,
    )
    return any(
        item["Key"].endswith("/manifest.json")
        for item in response.get("Contents", [])
    )


def _backup_prefixes(client, config, created_at):
    stamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    daily = (
        f"{config.prefix}/daily/{created_at:%Y/%m/%d}/"
        f"{stamp}-{run_id}"
    )
    monthly_root = f"{config.prefix}/monthly/{created_at:%Y/%m}"
    monthly = None
    if not _prefix_has_complete_backup(client, config, monthly_root):
        monthly = f"{monthly_root}/{stamp}-{run_id}"
    return daily, monthly


def perform_backup(*, storage=None, created_at=None):
    config = BackupConfig.from_settings()
    created_at = created_at or timezone.now()
    client = build_backup_client(config)
    daily_prefix, monthly_prefix = _backup_prefixes(client, config, created_at)
    retain_until = created_at + timedelta(days=config.object_lock_days)

    with tempfile.TemporaryDirectory(prefix="overtone-backup-") as temp_directory:
        temp_path = Path(temp_directory)
        database_path = temp_path / "database.dump"
        media_path = temp_path / "media.tar.gz"
        manifest_path = temp_path / "manifest.json"

        create_database_dump(database_path)
        media_result = create_media_archive(
            media_path,
            storage=storage,
            created_at=created_at,
        )

        payloads = [
            BackupFile(
                filename="database.dump",
                path=database_path,
                size=database_path.stat().st_size,
                sha256=_sha256(database_path),
                content_type="application/octet-stream",
            ),
            BackupFile(
                filename="media.tar.gz",
                path=media_path,
                size=media_path.stat().st_size,
                sha256=_sha256(media_path),
                content_type="application/gzip",
            ),
        ]
        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "created_at": created_at.isoformat(),
            "media_file_count": media_result["file_count"],
            "media_source_bytes": media_result["source_bytes"],
            "files": {
                item.filename: {"size": item.size, "sha256": item.sha256}
                for item in payloads
            },
        }
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        manifest_file = BackupFile(
            filename="manifest.json",
            path=manifest_path,
            size=manifest_path.stat().st_size,
            sha256=_sha256(manifest_path),
            content_type="application/json",
        )

        destinations = [daily_prefix]
        if monthly_prefix:
            destinations.append(monthly_prefix)
        for prefix in destinations:
            for backup_file in [*payloads, manifest_file]:
                _upload_and_verify(
                    client,
                    config,
                    backup_file,
                    f"{prefix}/{backup_file.filename}",
                    retain_until,
                )

    return {
        "daily_prefix": daily_prefix,
        "monthly_prefix": monthly_prefix,
        "media_file_count": media_result["file_count"],
        "source_bytes": sum(item.size for item in payloads),
        "object_count": 3 * len(destinations),
        "object_lock_until": retain_until.isoformat(),
    }


def latest_complete_backup_prefix(client, config):
    paginator = client.get_paginator("list_objects_v2")
    manifests = []
    for page in paginator.paginate(
        Bucket=config.bucket_name,
        Prefix=f"{config.prefix}/daily/",
    ):
        manifests.extend(
            item["Key"]
            for item in page.get("Contents", [])
            if item["Key"].endswith("/manifest.json")
        )
    if not manifests:
        raise BackupError("No complete daily backup was found.")
    return max(manifests).rsplit("/", 1)[0]


def download_and_verify_backup(destination, *, prefix=None):
    config = BackupConfig.from_settings()
    client = build_backup_client(config)
    prefix = prefix.strip().strip("/") if prefix else latest_complete_backup_prefix(
        client,
        config,
    )
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    manifest_path = destination / "manifest.json"
    client.download_file(
        config.bucket_name,
        f"{prefix}/manifest.json",
        str(manifest_path),
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError("Backup manifest could not be read.") from exc
    if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise BackupError("Backup manifest version is not supported.")

    required_files = {"database.dump", "media.tar.gz"}
    if set(manifest.get("files", {})) != required_files:
        raise BackupError("Backup manifest does not contain the expected files.")
    for filename, expected in manifest["files"].items():
        path = destination / filename
        client.download_file(config.bucket_name, f"{prefix}/{filename}", str(path))
        if path.stat().st_size != expected["size"] or _sha256(path) != expected["sha256"]:
            raise BackupError(f"Downloaded backup verification failed for {filename}.")
    return prefix, manifest


def extract_and_verify_media(archive_path, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise BackupError("The media restore directory must be empty.")

    with tarfile.open(archive_path, "r:gz") as archive:
        try:
            manifest_member = archive.getmember(MEDIA_MANIFEST_NAME)
            manifest_source = archive.extractfile(manifest_member)
            manifest = json.load(manifest_source)
        except (KeyError, OSError, json.JSONDecodeError, TypeError) as exc:
            raise BackupError("Media archive manifest is missing or invalid.") from exc

        expected = {item["name"]: item for item in manifest.get("files", [])}
        archive_names = {
            member.name for member in archive.getmembers() if member.isfile()
        }
        if archive_names != set(expected) | {MEDIA_MANIFEST_NAME}:
            raise BackupError("Media archive contents do not match its manifest.")

        for name, metadata in expected.items():
            safe_name = _safe_storage_name(name)
            source = archive.extractfile(archive.getmember(safe_name))
            target = destination / safe_name
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size = 0
            with target.open("wb") as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if size != metadata["size"] or digest.hexdigest() != metadata["sha256"]:
                raise BackupError(f"Restored media verification failed for {name}.")

    return len(expected)

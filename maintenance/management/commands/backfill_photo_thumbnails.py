from django.core.management.base import BaseCommand, CommandError

from maintenance.models import Company, Photo
from maintenance.photo_processing import build_photo_thumbnail


class Command(BaseCommand):
    help = "Generate missing piano-card thumbnails one photo at a time."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company-id",
            type=int,
            help="Limit the backfill to one company ID.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Process at most this many photos.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the number of missing thumbnails without reading images.",
        )

    def handle(self, *args, **options):
        company_id = options.get("company_id")
        limit = options.get("limit")
        dry_run = options["dry_run"]

        if limit is not None and limit < 1:
            raise CommandError("--limit must be greater than zero.")
        if company_id is not None and not Company.objects.filter(pk=company_id).exists():
            raise CommandError("Specified company was not found.")

        photos = Photo.objects.filter(thumbnail="").exclude(image="").order_by("pk")
        if company_id is not None:
            photos = photos.filter(company_id=company_id)
        if limit is not None:
            photos = photos[:limit]

        if dry_run:
            self.stdout.write(f"Missing thumbnails: {photos.count()}")
            return

        created = 0
        skipped = 0
        for photo in photos.iterator(chunk_size=25):
            try:
                thumbnail = build_photo_thumbnail(photo.image)
                if thumbnail is None:
                    skipped += 1
                    continue
                photo.thumbnail.save(thumbnail.name, thumbnail, save=False)
                Photo.objects.filter(pk=photo.pk).update(
                    thumbnail=photo.thumbnail.name,
                )
                created += 1
            finally:
                photo.image.close()

        self.stdout.write(self.style.SUCCESS(
            f"Thumbnail backfill complete. Created: {created} | Skipped: {skipped}"
        ))

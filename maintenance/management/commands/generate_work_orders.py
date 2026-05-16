r"""
Generate preventive work orders for due maintenance schedules.

Run manually:
    python3 manage.py generate_work_orders
    python3 manage.py generate_work_orders --dry-run

Hourly cron example:
    0 * * * * cd /path/to/Overtone && /usr/bin/env python3 manage.py generate_work_orders >> /tmp/overtone_generate_work_orders.log 2>&1
"""

from django.core.management.base import BaseCommand, CommandError

from maintenance.models import Company
from maintenance.services import generate_scheduled_work_orders


class Command(BaseCommand):
    help = "Generate WorkOrders for due built-in and custom maintenance schedules."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be created without saving anything.",
        )
        parser.add_argument(
            "--company-id",
            type=int,
            help="Limit generation to a single company by ID.",
        )
        parser.add_argument(
            "--company-slug",
            help="Limit generation to a single company by slug.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        company_id = options.get("company_id")
        company_slug = options.get("company_slug")

        company = None
        if company_id and company_slug:
            raise CommandError("Use only one of --company-id or --company-slug.")
        try:
            if company_id:
                company = Company.objects.get(pk=company_id)
            elif company_slug:
                company = Company.objects.get(slug=company_slug)
        except Company.DoesNotExist as exc:
            raise CommandError("Specified company was not found.") from exc

        if dry_run:
            self.stdout.write(self.style.WARNING("--- DRY RUN: nothing will be saved ---"))
        if company:
            self.stdout.write(f"Target company: {company.name} ({company.slug})")

        result = generate_scheduled_work_orders(dry_run=dry_run, company=company)
        for message in result.messages:
            self.stdout.write(message)

        self.stdout.write(self.style.SUCCESS(
            "\nDone. Created: {created} | Skipped existing: {existing} | "
            "Skipped not due: {not_due}".format(
                created=result.created,
                existing=result.skipped_existing,
                not_due=result.skipped_not_due,
            )
        ))

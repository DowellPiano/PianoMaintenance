r"""
Generate preventive work orders for due maintenance schedules.

Run manually:
    python3 manage.py generate_work_orders
    python3 manage.py generate_work_orders --dry-run

Hourly cron example:
    0 * * * * cd /Users/tom/Desktop/Limble\ Clone/PianoMaintenance && /usr/bin/env python3 manage.py generate_work_orders >> /tmp/piano_generate_work_orders.log 2>&1
"""

from django.core.management.base import BaseCommand

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

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("--- DRY RUN: nothing will be saved ---"))

        result = generate_scheduled_work_orders(dry_run=dry_run)
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

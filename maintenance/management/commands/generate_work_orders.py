"""
Management command: generate_work_orders

Usage:
    python manage.py generate_work_orders
    python manage.py generate_work_orders --dry-run

For every active MaintenanceSchedule this command:
  1. Determines the anchor date in priority order:
       a. schedule.last_service_date  (set whenever a work order is completed)
       b. piano.date_acquired         (fallback when no service has ever occurred)
       c. today                       (last resort)
  2. Computes next_due = anchor + interval_days.
  3. Creates a new Open/Preventive WorkOrder if:
       - next_due <= today + warning_days_before (i.e. due or coming due soon), AND
       - no Open or In-Progress WorkOrder already exists for this schedule.
"""

import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from maintenance.models import MaintenanceSchedule, WorkOrder

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate WorkOrders for overdue or never-serviced MaintenanceSchedules."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be created without actually saving anything.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        today = date.today()

        if dry_run:
            self.stdout.write(self.style.WARNING("--- DRY RUN — nothing will be saved ---"))

        active_schedules = (
            MaintenanceSchedule.objects
            .filter(is_active=True)
            .select_related("piano")
        )

        created = 0
        skipped_existing = 0
        skipped_not_due = 0

        for schedule in active_schedules:
            piano = schedule.piano

            # ------------------------------------------------------------------
            # 1.  Skip if an open / in-progress WO already exists for this schedule.
            # ------------------------------------------------------------------
            open_statuses = [WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS]
            if WorkOrder.objects.filter(schedule=schedule, status__in=open_statuses).exists():
                skipped_existing += 1
                logger.debug(
                    "Skipping schedule %s (piano: %s) — open WO already exists.",
                    schedule.pk,
                    piano,
                )
                continue

            # ------------------------------------------------------------------
            # 2.  Determine the anchor date for next-due calculation.
            #     Priority: last_service_date > piano.date_acquired > today
            # ------------------------------------------------------------------
            if schedule.last_service_date:
                anchor = schedule.last_service_date
                anchor_source = "last_service_date"
            elif piano.date_acquired:
                anchor = piano.date_acquired
                anchor_source = "piano.date_acquired"
            else:
                anchor = today
                anchor_source = "today (no history)"

            next_due = anchor + timedelta(days=schedule.interval_days)
            warn_from = next_due - timedelta(days=schedule.warning_days_before)

            # ------------------------------------------------------------------
            # 3.  Decide whether to create a WorkOrder.
            # ------------------------------------------------------------------
            if today < warn_from:
                skipped_not_due += 1
                logger.debug(
                    "Skipping schedule %s — not due until %s (warning from %s).",
                    schedule.pk,
                    next_due,
                    warn_from,
                )
                continue

            reason = (
                f"anchor={anchor} ({anchor_source}), "
                f"next_due={next_due}, warn_from={warn_from}"
            )

            # ------------------------------------------------------------------
            # 4.  Create the WorkOrder.
            # ------------------------------------------------------------------
            description = (
                f"Auto-generated preventive work order for '{schedule.task_name}' "
                f"on {piano}. Reason: {reason}."
            )

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[DRY RUN] Would create WO — Piano: {piano} | "
                        f"Schedule: {schedule.task_name} | {reason}"
                    )
                )
            else:
                WorkOrder.objects.create(
                    piano=piano,
                    schedule=schedule,
                    order_type=WorkOrder.OrderType.PREVENTIVE,
                    status=WorkOrder.Status.OPEN,
                    priority=WorkOrder.Priority.NORMAL,
                    description=description,
                    due_date=next_due,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created WO — Piano: {piano} | Schedule: {schedule.task_name} | {reason}"
                    )
                )
            created += 1

        # ------------------------------------------------------------------
        # 5.  Summary
        # ------------------------------------------------------------------
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Created: {created} | "
                f"Skipped (open WO exists): {skipped_existing} | "
                f"Skipped (not due yet): {skipped_not_due}"
            )
        )

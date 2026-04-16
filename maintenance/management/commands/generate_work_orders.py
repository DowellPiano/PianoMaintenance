"""
Management command: generate_work_orders

Usage:
    python manage.py generate_work_orders
    python manage.py generate_work_orders --dry-run

For every active MaintenanceSchedule this command:
  1. Looks up the most recent MaintenanceLog for the piano whose
     work_order__schedule matches the schedule (same task type is used
     as a fallback when no schedule FK exists on the log).
  2. Computes whether the interval has elapsed since that log.
  3. Creates a new Open/Preventive WorkOrder if needed, unless one is
     already Open or In Progress for that schedule.
"""

import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from maintenance.models import MaintenanceSchedule, MaintenanceLog, WorkOrder

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
            MaintenanceSchedule.objects.filter(is_active=True)
            .select_related("piano")
        )

        created = 0
        skipped_existing = 0
        skipped_not_due = 0

        for schedule in active_schedules:
            piano = schedule.piano

            # ------------------------------------------------------------------
            # 1.  Check for an already-open / in-progress WorkOrder for this
            #     schedule so we don't create duplicates.
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
            # 2.  Find the most recent MaintenanceLog for this piano & schedule.
            #     Primary: logs tied to a WO that uses this schedule.
            #     Fallback: any log for this piano whose WO matches the task type.
            # ------------------------------------------------------------------
            last_log = (
                MaintenanceLog.objects.filter(
                    piano=piano,
                    work_order__schedule=schedule,
                )
                .order_by("-logged_at")
                .first()
            )

            if last_log is None:
                # Fallback: check logs for the same piano via task_type on the
                # schedule linked to those WOs.
                last_log = (
                    MaintenanceLog.objects.filter(
                        piano=piano,
                        work_order__schedule__task_type=schedule.task_type,
                    )
                    .order_by("-logged_at")
                    .first()
                )

            # ------------------------------------------------------------------
            # 3.  Determine whether a new WorkOrder is needed.
            # ------------------------------------------------------------------
            needs_work_order = False

            if last_log is None:
                # Never serviced — create immediately.
                needs_work_order = True
                reason = "never serviced"
            else:
                last_date = last_log.logged_at.date()
                next_due = last_date + timedelta(days=schedule.interval_days)
                warn_from = next_due - timedelta(days=schedule.warning_days_before)

                if today >= warn_from:
                    needs_work_order = True
                    reason = (
                        f"due {next_due} (warning window started {warn_from})"
                    )
                else:
                    skipped_not_due += 1
                    logger.debug(
                        "Skipping schedule %s — not due until %s.", schedule.pk, next_due
                    )
                    continue

            # ------------------------------------------------------------------
            # 4.  Create the WorkOrder.
            # ------------------------------------------------------------------
            if needs_work_order:
                description = (
                    f"Auto-generated preventive work order for '{schedule.task_name}' "
                    f"on {piano}. Reason: {reason}."
                )

                if dry_run:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[DRY RUN] Would create WO — Piano: {piano} | "
                            f"Schedule: {schedule.task_name} | Reason: {reason}"
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

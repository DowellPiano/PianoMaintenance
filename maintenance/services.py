from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import MaintenanceSchedule, Piano, WorkOrder


@dataclass
class WorkOrderGenerationResult:
    created: int = 0
    skipped_existing: int = 0
    skipped_not_due: int = 0
    messages: list[str] = field(default_factory=list)


def generate_scheduled_work_orders(today=None, dry_run=False):
    """
    Create preventive work orders for due piano maintenance.

    This is intentionally request-independent so it can be run from cron via
    the generate_work_orders management command.
    """
    today = today or date.today()
    result = WorkOrderGenerationResult()
    open_statuses = [WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS]

    built_in_types = [
        ('Tuning', 'next_tuning_due', 'tuning_interval_value'),
        ('Regulation', 'next_regulation_due', 'regulation_interval_value'),
        ('Voicing', 'next_voicing_due', 'voicing_interval_value'),
        ('Cleaning', 'next_cleaning_due', 'cleaning_interval_value'),
    ]

    for piano in Piano.objects.filter(is_active=True):
        needs_save = []
        for task_type, due_field, interval_field in built_in_types:
            due_date = getattr(piano, due_field)
            interval_val = getattr(piano, interval_field)

            if due_date is None and interval_val:
                due_date = today
                if not dry_run:
                    setattr(piano, due_field, today)
                    needs_save.append(due_field)

            if not due_date or due_date > today:
                result.skipped_not_due += 1
                continue

            exists = WorkOrder.objects.filter(
                piano=piano,
                task_type=task_type,
                status__in=open_statuses,
            ).exists()
            if exists:
                result.skipped_existing += 1
                continue

            message = f"Built-in {task_type} for {piano} due {due_date}"
            if dry_run:
                result.messages.append(f"[DRY RUN] Would create WO: {message}")
            else:
                WorkOrder.objects.create(
                    piano=piano,
                    order_type=WorkOrder.OrderType.PREVENTIVE,
                    task_type=task_type,
                    status=WorkOrder.Status.OPEN,
                    priority=WorkOrder.Priority.NORMAL,
                    description=f"Scheduled {task_type.lower()}",
                    due_date=due_date,
                )
                result.messages.append(f"Created WO: {message}")
            result.created += 1

        if needs_save:
            piano.save(update_fields=needs_save)

    for sched in MaintenanceSchedule.objects.filter(is_active=True).select_related('piano'):
        exists = WorkOrder.objects.filter(
            piano=sched.piano,
            schedule=sched,
            status__in=open_statuses,
        ).exists()
        if exists:
            result.skipped_existing += 1
            continue

        anchor = sched.last_service_date or today
        next_due = anchor + timedelta(days=sched.interval_days)
        warn_from = next_due - timedelta(days=sched.warning_days_before)
        if today < warn_from:
            result.skipped_not_due += 1
            continue

        message = f"Schedule {sched.task_name} for {sched.piano} due {next_due}"
        if dry_run:
            result.messages.append(f"[DRY RUN] Would create WO: {message}")
        else:
            WorkOrder.objects.create(
                piano=sched.piano,
                order_type=WorkOrder.OrderType.PREVENTIVE,
                task_type=sched.task_type,
                status=WorkOrder.Status.OPEN,
                priority=WorkOrder.Priority.NORMAL,
                description=f"Scheduled: {sched.task_name}",
                due_date=next_due,
                schedule=sched,
            )
            result.messages.append(f"Created WO: {message}")
        result.created += 1

    return result

from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import (
    CompanyInvitation,
    CompanyMembership,
    CompanySettings,
    MaintenanceSchedule,
    Organization,
    Piano,
    Venue,
    WorkOrder,
)


@dataclass
class WorkOrderGenerationResult:
    created: int = 0
    skipped_existing: int = 0
    skipped_not_due: int = 0
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompanySetupTask:
    key: str
    title: str
    detail: str
    is_complete: bool
    cta_label: str


@dataclass(frozen=True)
class CompanySetupProgress:
    tasks: list[CompanySetupTask]
    organization_count: int
    venue_count: int
    piano_count: int
    active_member_count: int
    pending_invitation_count: int

    @property
    def completed_count(self):
        return sum(1 for task in self.tasks if task.is_complete)

    @property
    def total_count(self):
        return len(self.tasks)

    @property
    def percent_complete(self):
        if not self.tasks:
            return 100
        return int((self.completed_count / self.total_count) * 100)

    @property
    def is_complete(self):
        return all(task.is_complete for task in self.tasks)


def build_company_setup_progress(
    company,
    *,
    company_settings=None,
    organization_count=None,
    venue_count=None,
    piano_count=None,
):
    if company_settings is None:
        company_settings = CompanySettings.objects.filter(company=company).first()
    if organization_count is None:
        organization_count = Organization.objects.filter(company=company).count()
    if venue_count is None:
        venue_count = Venue.objects.filter(company=company).count()
    if piano_count is None:
        piano_count = Piano.objects.filter(company=company, is_active=True).count()
    active_member_count = CompanyMembership.objects.filter(
        company=company,
        is_active=True,
        user__is_active=True,
    ).count()
    pending_invitation_count = CompanyInvitation.objects.filter(
        company=company,
        status=CompanyInvitation.Status.PENDING,
    ).count()

    profile_complete = bool(
        company_settings
        and (company_settings.company_name or company.name)
        and (company_settings.email or company_settings.phone or company_settings.address)
    )
    team_complete = active_member_count > 1 or pending_invitation_count > 0

    tasks = [
        CompanySetupTask(
            key="company_profile",
            title="Complete company profile",
            detail="Add contact details and default labor settings for this company.",
            is_complete=profile_complete,
            cta_label="Open Settings",
        ),
        CompanySetupTask(
            key="team",
            title="Add your team",
            detail="Invite another admin or technician so the company is not dependent on one login.",
            is_complete=team_complete,
            cta_label="Invite Teammate",
        ),
        CompanySetupTask(
            key="organizations",
            title="Create an organization",
            detail="Add the school, church, venue group, or client account you serve.",
            is_complete=organization_count > 0,
            cta_label="Add Organization",
        ),
        CompanySetupTask(
            key="venues",
            title="Create a venue",
            detail="Set up the physical location technicians travel to.",
            is_complete=venue_count > 0,
            cta_label="Add Venue",
        ),
        CompanySetupTask(
            key="pianos",
            title="Add your first piano",
            detail="Create at least one active piano so work orders and schedules have something to run against.",
            is_complete=piano_count > 0,
            cta_label="Add Piano",
        ),
    ]

    return CompanySetupProgress(
        tasks=tasks,
        organization_count=organization_count,
        venue_count=venue_count,
        piano_count=piano_count,
        active_member_count=active_member_count,
        pending_invitation_count=pending_invitation_count,
    )


def generate_scheduled_work_orders(today=None, dry_run=False, company=None):
    """
    Create preventive work orders for due piano maintenance.

    This is intentionally request-independent so it can be run from cron via
    the generate_work_orders management command.
    """
    today = today or date.today()
    result = WorkOrderGenerationResult()
    open_statuses = [WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS]

    built_in_types = [
        ('Tuning', 'next_tuning_due', 'tuning_interval_value', 'tuning_interval_unit'),
        ('Regulation', 'next_regulation_due', 'regulation_interval_value', 'regulation_interval_unit'),
        ('Voicing', 'next_voicing_due', 'voicing_interval_value', 'voicing_interval_unit'),
        ('Cleaning', 'next_cleaning_due', 'cleaning_interval_value', 'cleaning_interval_unit'),
    ]

    piano_qs = Piano.objects.filter(is_active=True)
    if company is not None:
        piano_qs = piano_qs.filter(company=company)

    for piano in piano_qs:
        needs_save = []
        for task_type, due_field, interval_value_field, interval_unit_field in built_in_types:
            stored_due_date = getattr(piano, due_field)
            due_date = stored_due_date
            interval_val = getattr(piano, interval_value_field)
            interval_unit = getattr(piano, interval_unit_field)

            if interval_val:
                last_completed = WorkOrder.objects.filter(
                    company=piano.company,
                    piano=piano,
                    task_type=task_type,
                    status=WorkOrder.Status.COMPLETE,
                    completed_date__isnull=False,
                ).order_by('-completed_date', '-pk').first()
                if last_completed:
                    interval_days = piano._interval_to_days(interval_val, interval_unit)
                    due_date = last_completed.completed_date + timedelta(days=interval_days)

            if due_date != stored_due_date:
                if dry_run:
                    result.messages.append(
                        f"[DRY RUN] Would update {piano} {task_type} next due to {due_date}"
                    )
                else:
                    setattr(piano, due_field, due_date)
                    needs_save.append(due_field)

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
                    company=piano.company,
                    piano=piano,
                    order_type=WorkOrder.OrderType.PREVENTIVE,
                    task_type=task_type,
                    status=WorkOrder.Status.OPEN,
                    priority=WorkOrder.Priority.NORMAL,
                    is_team_job=False,
                    description=f"Scheduled {task_type.lower()}",
                    due_date=due_date,
                )
                result.messages.append(f"Created WO: {message}")
            result.created += 1

        if needs_save:
            piano.save(update_fields=needs_save)

    schedule_qs = MaintenanceSchedule.objects.filter(
        is_active=True,
        piano__is_active=True,
    ).select_related('piano')
    if company is not None:
        schedule_qs = schedule_qs.filter(company=company)

    for sched in schedule_qs:
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
                company=sched.company,
                piano=sched.piano,
                order_type=WorkOrder.OrderType.PREVENTIVE,
                task_type=sched.task_type,
                status=WorkOrder.Status.OPEN,
                priority=WorkOrder.Priority.NORMAL,
                is_team_job=False,
                description=f"Scheduled: {sched.task_name}",
                due_date=next_due,
                schedule=sched,
            )
            result.messages.append(f"Created WO: {message}")
        result.created += 1

    return result

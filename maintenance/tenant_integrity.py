from dataclasses import dataclass

from django.db.models import Exists, F, OuterRef, Q

from .models import (
    CompanyMembership,
    ConditionReading,
    MaintenanceLog,
    MaintenanceRequest,
    MaintenanceSchedule,
    PartUsed,
    Photo,
    Piano,
    Venue,
    WorkOrder,
)


@dataclass(frozen=True)
class TenantIntegrityResult:
    name: str
    violations: int


def _nullable_relation_mismatch(left, right):
    left_null = f"{left}__isnull"
    right_null = f"{right}__isnull"
    left_id = f"{left}_id"
    right_id = f"{right}_id"
    return (
        Q(**{left_null: True, right_null: False})
        | Q(**{left_null: False, right_null: True})
        | (
            Q(**{left_null: False, right_null: False})
            & ~Q(**{left_id: F(right_id)})
        )
    )


def run_tenant_integrity_checks():
    assignee_membership = CompanyMembership.objects.filter(
        company_id=OuterRef("company_id"),
        user_id=OuterRef("assigned_tech_id"),
    )
    log_technician_membership = CompanyMembership.objects.filter(
        company_id=OuterRef("company_id"),
        user_id=OuterRef("technician_id"),
    )

    checks = [
        (
            "venue.organization_company",
            Venue.objects.filter(organization__isnull=False).exclude(
                company_id=F("organization__company_id")
            ),
        ),
        (
            "piano.venue_company",
            Piano.objects.filter(venue__isnull=False).exclude(
                company_id=F("venue__company_id")
            ),
        ),
        (
            "piano.tag_company",
            Piano.tags.through.objects.exclude(
                piano__company_id=F("tag__company_id")
            ),
        ),
        (
            "schedule.piano_company",
            MaintenanceSchedule.objects.exclude(
                company_id=F("piano__company_id")
            ),
        ),
        (
            "schedule.template_company",
            MaintenanceSchedule.objects.filter(template__isnull=False).exclude(
                company_id=F("template__company_id")
            ),
        ),
        (
            "work_order.piano_company",
            WorkOrder.objects.filter(piano__isnull=False).exclude(
                company_id=F("piano__company_id")
            ),
        ),
        (
            "work_order.schedule_company",
            WorkOrder.objects.filter(schedule__isnull=False).exclude(
                company_id=F("schedule__company_id")
            ),
        ),
        (
            "work_order.schedule_piano",
            WorkOrder.objects.filter(schedule__isnull=False).filter(
                _nullable_relation_mismatch("piano", "schedule__piano")
            ),
        ),
        (
            "work_order.assignee_membership",
            WorkOrder.objects.filter(assigned_tech__isnull=False)
            .annotate(_has_company_membership=Exists(assignee_membership))
            .filter(_has_company_membership=False),
        ),
        (
            "maintenance_log.work_order_company",
            MaintenanceLog.objects.exclude(
                company_id=F("work_order__company_id")
            ),
        ),
        (
            "maintenance_log.piano_company",
            MaintenanceLog.objects.filter(piano__isnull=False).exclude(
                company_id=F("piano__company_id")
            ),
        ),
        (
            "maintenance_log.work_order_piano",
            MaintenanceLog.objects.filter(
                _nullable_relation_mismatch("piano", "work_order__piano")
            ),
        ),
        (
            "maintenance_log.technician_membership",
            MaintenanceLog.objects.annotate(
                _has_company_membership=Exists(log_technician_membership)
            ).filter(_has_company_membership=False),
        ),
        (
            "condition_reading.piano_company",
            ConditionReading.objects.filter(piano__isnull=False).exclude(
                company_id=F("piano__company_id")
            ),
        ),
        (
            "condition_reading.log_company",
            ConditionReading.objects.filter(log__isnull=False).exclude(
                company_id=F("log__company_id")
            ),
        ),
        (
            "condition_reading.log_piano",
            ConditionReading.objects.filter(log__isnull=False).filter(
                _nullable_relation_mismatch("piano", "log__piano")
            ),
        ),
        (
            "part_used.log_company",
            PartUsed.objects.exclude(company_id=F("log__company_id")),
        ),
        (
            "part_used.part_company",
            PartUsed.objects.exclude(company_id=F("part__company_id")),
        ),
        (
            "maintenance_request.piano_company",
            MaintenanceRequest.objects.filter(piano__isnull=False).exclude(
                company_id=F("piano__company_id")
            ),
        ),
        (
            "maintenance_request.work_order_company",
            MaintenanceRequest.objects.filter(work_order__isnull=False).exclude(
                company_id=F("work_order__company_id")
            ),
        ),
        (
            "maintenance_request.work_order_piano",
            MaintenanceRequest.objects.filter(work_order__isnull=False).filter(
                _nullable_relation_mismatch("piano", "work_order__piano")
            ),
        ),
        (
            "photo.piano_company",
            Photo.objects.filter(piano__isnull=False).exclude(
                company_id=F("piano__company_id")
            ),
        ),
        (
            "photo.work_order_company",
            Photo.objects.filter(work_order__isnull=False).exclude(
                company_id=F("work_order__company_id")
            ),
        ),
        (
            "photo.work_order_piano",
            Photo.objects.filter(
                piano__isnull=False,
                work_order__piano__isnull=False,
            ).exclude(piano_id=F("work_order__piano_id")),
        ),
    ]

    return [
        TenantIntegrityResult(name=name, violations=queryset.count())
        for name, queryset in checks
    ]

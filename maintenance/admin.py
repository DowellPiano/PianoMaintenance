from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count

from .models import (
    Location,
    Piano,
    Technician,
    Team,
    ScheduleTemplate,
    MaintenanceSchedule,
    WorkOrder,
    MaintenanceLog,
    ConditionReading,
    Part,
    PartUsed,
    MaintenanceRequest,
)


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------
@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display  = ("name", "building", "address")
    search_fields = ("name", "building", "address")
    # No FK columns in list_display — no select_related needed.


# ---------------------------------------------------------------------------
# Piano
# ---------------------------------------------------------------------------
@admin.register(Piano)
class PianoAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "brand",
        "model",
        "piano_type",
        "location",
        "serial_number",
        "year_built",
        "year_acquired",
    )
    list_filter    = ("piano_type", "location", "brand")
    search_fields  = ("name", "brand", "model", "serial_number")
    readonly_fields = ("qr_code_token",)

    def get_queryset(self, request):
        # location column — join instead of per-row query
        return super().get_queryset(request).select_related("location")


# ---------------------------------------------------------------------------
# Technician
# ---------------------------------------------------------------------------
@admin.register(Technician)
class TechnicianAdmin(UserAdmin):
    list_display = (
        "username",
        "first_name",
        "last_name",
        "email",
        "is_active",
        "is_staff",
    )
    list_filter   = ("is_active", "is_staff", "groups")
    search_fields = ("username", "first_name", "last_name", "email")
    # No FK columns in list_display — no select_related needed.


# ---------------------------------------------------------------------------
# ScheduleTemplate
# ---------------------------------------------------------------------------
class MaintenanceScheduleInline(admin.TabularInline):
    model          = MaintenanceSchedule
    extra          = 0
    fields         = ("piano", "task_name", "interval_days", "is_active")
    readonly_fields = ("piano",)
    show_change_link = True


@admin.register(ScheduleTemplate)
class ScheduleTemplateAdmin(admin.ModelAdmin):
    list_display  = ("name", "task_type", "interval_days", "warning_days_before", "schedule_count")
    list_filter   = ("task_type",)
    search_fields = ("name", "task_name")
    inlines       = [MaintenanceScheduleInline]

    def get_queryset(self, request):
        # Annotate once per page load instead of one .count() query per row.
        return super().get_queryset(request).annotate(_schedule_count=Count("schedules"))

    @admin.display(description="Schedules applied")
    def schedule_count(self, obj):
        return obj._schedule_count


# ---------------------------------------------------------------------------
# MaintenanceSchedule
# ---------------------------------------------------------------------------
@admin.register(MaintenanceSchedule)
class MaintenanceScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "task_name",
        "piano",
        "task_type",
        "interval_days",
        "warning_days_before",
        "is_active",
    )
    list_filter   = ("task_type", "is_active", "piano__location")
    search_fields = ("task_name", "piano__name", "piano__brand")

    def get_queryset(self, request):
        # piano column + piano__location filter — one join covers both
        return super().get_queryset(request).select_related("piano__location", "template")


# ---------------------------------------------------------------------------
# WorkOrder
# ---------------------------------------------------------------------------
class MaintenanceLogInline(admin.TabularInline):
    model          = MaintenanceLog
    extra          = 0
    fields         = ("technician", "hours_worked", "work_performed", "logged_at")
    readonly_fields = ("logged_at",)


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "piano",
        "order_type",
        "status",
        "priority",
        "assigned_tech",
        "due_date",
        "created_at",
    )
    list_filter    = ("status", "order_type", "priority", "piano__location")
    search_fields  = ("piano__name", "piano__brand", "description")
    raw_id_fields  = ("piano", "assigned_tech", "schedule")
    readonly_fields = ("created_at",)
    inlines        = [MaintenanceLogInline]

    def get_queryset(self, request):
        # piano + assigned_tech columns; piano__location for list_filter
        return super().get_queryset(request).select_related(
            "piano__location", "assigned_tech"
        )


# ---------------------------------------------------------------------------
# MaintenanceLog
# ---------------------------------------------------------------------------
class PartUsedInline(admin.TabularInline):
    model  = PartUsed
    extra  = 0
    fields = ("part", "quantity_used", "cost_at_time")


class ConditionReadingInline(admin.TabularInline):
    model  = ConditionReading
    extra  = 0
    fields = (
        "overall_rating",
        "pitch_before_cents",
        "pitch_after_cents",
        "humidity_pct",
        "temperature_f",
        "recorded_at",
    )
    readonly_fields = ("recorded_at",)


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "piano",
        "technician",
        "work_order",
        "hours_worked",
        "logged_at",
    )
    list_filter   = ("technician", "piano__location")
    search_fields = ("piano__name", "technician__username", "work_performed")
    readonly_fields = ("logged_at",)
    inlines       = [PartUsedInline, ConditionReadingInline]

    def get_queryset(self, request):
        # piano + technician + work_order columns
        return super().get_queryset(request).select_related(
            "piano__location", "technician", "work_order"
        )


# ---------------------------------------------------------------------------
# ConditionReading
# ---------------------------------------------------------------------------
@admin.register(ConditionReading)
class ConditionReadingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "piano",
        "overall_rating",
        "pitch_before_cents",
        "pitch_after_cents",
        "humidity_pct",
        "temperature_f",
        "recorded_at",
    )
    list_filter   = ("overall_rating", "piano__location")
    search_fields = ("piano__name",)
    readonly_fields = ("recorded_at",)

    def get_queryset(self, request):
        # piano column
        return super().get_queryset(request).select_related("piano__location")


# ---------------------------------------------------------------------------
# Part
# ---------------------------------------------------------------------------
@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "part_number",
        "supplier",
        "unit_cost",
        "stock_quantity",
        "reorder_threshold",
        "needs_reorder",
    )
    list_filter   = ("supplier",)
    search_fields = ("name", "part_number", "supplier")
    # No FK columns in list_display — no select_related needed.

    @admin.display(boolean=True, description="Needs Reorder?")
    def needs_reorder(self, obj):
        return obj.needs_reorder


# ---------------------------------------------------------------------------
# PartUsed
# ---------------------------------------------------------------------------
@admin.register(PartUsed)
class PartUsedAdmin(admin.ModelAdmin):
    list_display  = ("id", "part", "log", "quantity_used", "cost_at_time")
    list_filter   = ("part",)
    search_fields = ("part__name", "part__part_number")

    def get_queryset(self, request):
        # part + log columns
        return super().get_queryset(request).select_related("part", "log")


# ---------------------------------------------------------------------------
# MaintenanceRequest
# ---------------------------------------------------------------------------
@admin.register(MaintenanceRequest)
class MaintenanceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "piano",
        "status",
        "reported_by_name",
        "reported_by_email",
        "work_order",
        "created_at",
    )
    list_filter   = ("status", "piano__location")
    search_fields = ("piano__name", "reported_by_name", "reported_by_email", "issue_description")
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        # piano + work_order columns; piano__location for list_filter
        return super().get_queryset(request).select_related("piano__location", "work_order")


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------
@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display  = ("name", "manager", "member_count", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("manager").annotate(
            _member_count=Count("members")
        )

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj._member_count

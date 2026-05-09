from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count

from .models import (
    Organization,
    Venue,
    Piano,
    Tag,
    Technician,
    ScheduleTemplate,
    MaintenanceSchedule,
    WorkOrder,
    MaintenanceLog,
    ConditionReading,
    Part,
    PartUsed,
    MaintenanceRequest,
    CompanySettings,
)


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------
@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display  = ("name", "short_name", "contact_name", "contact_email", "venue_count")
    search_fields = ("name", "short_name", "contact_name")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_venue_count=Count("venues"))

    @admin.display(description="Venues")
    def venue_count(self, obj):
        return obj._venue_count


# ---------------------------------------------------------------------------
# Venue
# ---------------------------------------------------------------------------
@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display  = ("name", "short_name", "organization", "address")
    list_filter   = ("organization",)
    search_fields = ("name", "short_name", "address")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("organization")


# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


# ---------------------------------------------------------------------------
# Piano
# ---------------------------------------------------------------------------
@admin.register(Piano)
class PianoAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "make",
        "model",
        "piano_type",
        "venue",
        "section",
        "room",
        "serial_number",
    )
    list_filter    = ("piano_type", "venue__organization", "venue", "make", "tags")
    search_fields  = ("name", "make", "model", "serial_number", "tags__name")
    filter_horizontal = ("tags",)
    readonly_fields = ("qr_code_token",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("venue__organization")


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
        "role_admin",
        "role_technician",
        "is_active",
    )
    list_filter   = ("role_admin", "role_technician", "is_active", "is_staff", "groups")
    search_fields = ("username", "first_name", "last_name", "email")
    # Add role fields to the user edit form
    fieldsets = UserAdmin.fieldsets + (
        ("App Roles", {"fields": ("role_admin", "role_technician")}),
    )


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
    list_filter   = ("task_type", "is_active", "piano__venue")
    search_fields = ("task_name", "piano__name", "piano__make")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("piano__venue", "template")


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
    list_filter    = ("status", "order_type", "priority", "piano__venue")
    search_fields  = ("piano__name", "piano__make", "description")
    raw_id_fields  = ("piano", "assigned_tech", "schedule")
    readonly_fields = ("created_at",)
    inlines        = [MaintenanceLogInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "piano__venue", "assigned_tech"
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
    list_filter   = ("technician", "piano__venue")
    search_fields = ("piano__name", "technician__username", "work_performed")
    readonly_fields = ("logged_at",)
    inlines       = [PartUsedInline, ConditionReadingInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "piano__venue", "technician", "work_order"
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
    list_filter   = ("overall_rating", "piano__venue")
    search_fields = ("piano__name",)
    readonly_fields = ("recorded_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("piano__venue")


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
    list_filter   = ("status", "piano__venue")
    search_fields = ("piano__name", "reported_by_name", "reported_by_email", "issue_description")
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("piano__venue", "work_order")


# ---------------------------------------------------------------------------
# CompanySettings (singleton)
# ---------------------------------------------------------------------------
@admin.register(CompanySettings)
class CompanySettingsAdmin(admin.ModelAdmin):
    list_display = ("company_name", "phone", "email", "default_labor_rate")

    def has_add_permission(self, request):
        # Only one instance allowed
        return not CompanySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False



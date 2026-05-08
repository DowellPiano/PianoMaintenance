import uuid
from datetime import date, timedelta
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator

YEAR_VALIDATORS = [MinValueValidator(1700), MaxValueValidator(2100)]


class ConditionLevel(models.TextChoices):
    EXCELLENT = "Excellent", "Excellent"
    GOOD = "Good", "Good"
    FAIR = "Fair", "Fair"
    POOR = "Poor", "Poor"
    NEEDS_ATTENTION = "Needs Immediate Attention", "Needs Immediate Attention"


class IntervalUnit(models.TextChoices):
    MONTHS = "months", "Months"
    DAYS = "days", "Days"


# ---------------------------------------------------------------------------
# Organization  (administrative owner — who signs the contract)
# ---------------------------------------------------------------------------
class Tag(models.Model):
    """Free-form label that can be attached to pianos."""
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Organization(models.Model):
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    contact_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.short_name or self.name


# ---------------------------------------------------------------------------
# Venue  (physical location a technician drives to)
# ---------------------------------------------------------------------------
class Venue(models.Model):
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=50, blank=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="venues",
    )
    address = models.TextField(blank=True)
    on_site_contact = models.TextField(blank=True,
        help_text="Local contact at this venue — name, role, phone.")
    parking_notes = models.TextField(blank=True)
    access_notes = models.TextField(blank=True,
        help_text="General access instructions for the building.")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["organization", "name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Piano
# ---------------------------------------------------------------------------
class Piano(models.Model):
    class PianoType(models.TextChoices):
        GRAND = "Grand", "Grand"
        UPRIGHT = "Upright", "Upright"
        DIGITAL = "Digital", "Digital"

    venue = models.ForeignKey(
        Venue, on_delete=models.PROTECT, related_name="pianos"
    )
    name = models.CharField(max_length=200)
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    piano_type = models.CharField(max_length=20, choices=PianoType.choices)
    year_built    = models.IntegerField(null=True, blank=True, validators=YEAR_VALIDATORS)
    year_acquired = models.IntegerField(null=True, blank=True, validators=YEAR_VALIDATORS)

    # -- Location within venue --------------------------------------------------
    section = models.CharField(max_length=200, blank=True,
        help_text="Optional grouping within venue (building, floor, wing).")
    room = models.CharField(max_length=200, blank=True,
        help_text="Specific spot — room name or number.")
    room_description = models.TextField(blank=True,
        help_text="Directions to help a first-time visitor find this room.")
    room_access_notes = models.TextField(blank=True,
        help_text="Key codes, access hours, or other entry instructions.")

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="pianos")
    qr_code_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # -- Maintenance intervals (core 4 types) --------------------------------
    tuning_interval_value = models.IntegerField(default=6)
    tuning_interval_unit = models.CharField(
        max_length=10, choices=IntervalUnit.choices, default=IntervalUnit.MONTHS
    )
    regulation_interval_value = models.IntegerField(default=12)
    regulation_interval_unit = models.CharField(
        max_length=10, choices=IntervalUnit.choices, default=IntervalUnit.MONTHS
    )
    voicing_interval_value = models.IntegerField(default=12)
    voicing_interval_unit = models.CharField(
        max_length=10, choices=IntervalUnit.choices, default=IntervalUnit.MONTHS
    )
    cleaning_interval_value = models.IntegerField(default=6)
    cleaning_interval_unit = models.CharField(
        max_length=10, choices=IntervalUnit.choices, default=IntervalUnit.MONTHS
    )

    # -- Next due dates (computed from intervals + last service) --------------
    next_tuning_due = models.DateField(null=True, blank=True)
    next_regulation_due = models.DateField(null=True, blank=True)
    next_voicing_due = models.DateField(null=True, blank=True)
    next_cleaning_due = models.DateField(null=True, blank=True)

    # -- Current environment (updated from latest ConditionReading) -----------
    current_pitch = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    current_humidity = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    current_temperature = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    # -- Current component conditions (updated from latest ConditionReading) --
    regulation_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    voicing_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    belly_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    soundboard_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    pinblock_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    strings_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    hammers_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    keys_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    pedals_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    case_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )

    CONDITION_FIELDS = [
        'regulation_condition', 'voicing_condition', 'belly_condition',
        'soundboard_condition', 'pinblock_condition', 'strings_condition',
        'hammers_condition', 'keys_condition', 'pedals_condition',
        'case_condition',
    ]

    class Meta:
        ordering = ["venue", "name"]

    def __str__(self):
        return f"{self.make} {self.model} — {self.name}".strip(" —")

    @property
    def has_any_condition(self):
        return any(getattr(self, f) for f in self.CONDITION_FIELDS)

    @property
    def condition_dots(self):
        mapping = {
            'Excellent': 'excellent', 'Good': 'good', 'Fair': 'fair',
            'Poor': 'poor', 'Needs Immediate Attention': 'attention',
        }
        return [mapping.get(getattr(self, f), '') for f in self.CONDITION_FIELDS if getattr(self, f)]

    @property
    def profile_photo(self):
        try:
            return self.photos.filter(is_profile_photo=True).first()
        except Exception:
            return None

    def _interval_to_days(self, value, unit):
        """Convert interval value + unit to timedelta days."""
        if unit == 'months':
            return value * 30
        return value

    def advance_schedule(self, task_type, completed_date):
        """
        After completing a work order of the given task_type, advance the
        corresponding next-due date on this piano.
        """
        mapping = {
            'Tuning': ('tuning_interval_value', 'tuning_interval_unit', 'next_tuning_due'),
            'Regulation': ('regulation_interval_value', 'regulation_interval_unit', 'next_regulation_due'),
            'Voicing': ('voicing_interval_value', 'voicing_interval_unit', 'next_voicing_due'),
            'Cleaning': ('cleaning_interval_value', 'cleaning_interval_unit', 'next_cleaning_due'),
        }
        if task_type in mapping:
            val_field, unit_field, due_field = mapping[task_type]
            days = self._interval_to_days(getattr(self, val_field), getattr(self, unit_field))
            setattr(self, due_field, completed_date + timedelta(days=days))
            self.save(update_fields=[due_field])


# ---------------------------------------------------------------------------
# Technician  (extends AbstractUser)
# ---------------------------------------------------------------------------
class Technician(AbstractUser):
    """
    Custom user model for piano technicians.
    Set AUTH_USER_MODEL = 'maintenance.Technician' in settings.py.
    is_active is already provided by AbstractUser; we declare it here
    explicitly to satisfy the spec and set the default clearly.
    """
    is_active = models.BooleanField(default=True)
    team = models.ForeignKey(
        'Team',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='members',
    )

    class Meta:
        verbose_name = "Technician"
        verbose_name_plural = "Technicians"

    def __str__(self):
        full = self.get_full_name()
        return full if full else self.username


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------
class Team(models.Model):
    name = models.CharField(max_length=200, unique=True)
    manager = models.ForeignKey(
        'Technician',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='managed_teams',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Shared task-type choices
# ---------------------------------------------------------------------------
class TaskType(models.TextChoices):
    TUNING = "Tuning", "Tuning"
    REGULATION = "Regulation", "Regulation"
    VOICING = "Voicing", "Voicing"
    CLEANING = "Cleaning", "Cleaning"
    INSPECTION = "Inspection", "Inspection"
    OTHER = "Other", "Other"


# ---------------------------------------------------------------------------
# ScheduleTemplate  (reusable blueprint)
# ---------------------------------------------------------------------------
class ScheduleTemplate(models.Model):
    name = models.CharField(max_length=200)
    task_name = models.CharField(max_length=200)
    task_type = models.CharField(max_length=20, choices=TaskType.choices)
    interval_days = models.IntegerField()
    warning_days_before = models.IntegerField(default=7)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# MaintenanceSchedule
# ---------------------------------------------------------------------------
class MaintenanceSchedule(models.Model):
    TaskType = TaskType  # keep existing references working

    piano = models.ForeignKey(
        Piano, on_delete=models.CASCADE, related_name="schedules"
    )
    template = models.ForeignKey(
        ScheduleTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="schedules",
    )
    task_name = models.CharField(max_length=200)
    task_type = models.CharField(max_length=20, choices=TaskType.choices)
    interval_days = models.IntegerField()
    warning_days_before = models.IntegerField(default=7)
    is_active = models.BooleanField(default=True)
    last_service_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["piano", "task_type"]

    def __str__(self):
        return f"{self.task_name} — every {self.interval_days}d"

    @property
    def next_due(self):
        if self.last_service_date:
            return self.last_service_date + timedelta(days=self.interval_days)
        return None

    @property
    def is_overdue(self):
        nd = self.next_due
        return nd is not None and nd < date.today()

    @property
    def is_due_soon(self):
        nd = self.next_due
        if nd is None:
            return False
        return nd <= date.today() + timedelta(days=self.warning_days_before)


# ---------------------------------------------------------------------------
# ServiceVisit  (one trip to a venue)
# ---------------------------------------------------------------------------
class ServiceVisit(models.Model):
    class VisitStatus(models.TextChoices):
        PLANNED = "Planned", "Planned"
        IN_PROGRESS = "In Progress", "In Progress"
        COMPLETE = "Complete", "Complete"

    technician = models.ForeignKey(
        Technician, on_delete=models.PROTECT, related_name="service_visits",
    )
    venue = models.ForeignKey(
        Venue, on_delete=models.PROTECT, related_name="service_visits",
    )
    date = models.DateField()
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    miles_driven = models.DecimalField(
        max_digits=6, decimal_places=1, null=True, blank=True,
    )
    status = models.CharField(
        max_length=20, choices=VisitStatus.choices, default=VisitStatus.PLANNED,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"Visit {self.date} — {self.venue.name}"

    @property
    def total_duration_minutes(self):
        """Time Out minus Time In, in minutes."""
        if self.time_in and self.time_out:
            from datetime import datetime
            t_in = datetime.combine(self.date, self.time_in)
            t_out = datetime.combine(self.date, self.time_out)
            return int((t_out - t_in).total_seconds() / 60)
        return None

    @property
    def total_duration_display(self):
        mins = self.total_duration_minutes
        if mins is None:
            return "—"
        hours, remainder = divmod(mins, 60)
        if hours and remainder:
            return f"{hours}h {remainder}m"
        elif hours:
            return f"{hours}h"
        return f"{mins}m"

    @property
    def work_order_count(self):
        return self.work_orders.count()


# ---------------------------------------------------------------------------
# WorkOrder
# ---------------------------------------------------------------------------
class WorkOrder(models.Model):
    class OrderType(models.TextChoices):
        PREVENTIVE = "Preventive", "Preventive"
        REQUEST = "Request", "Request"
        EMERGENCY = "Emergency", "Emergency"

    class Status(models.TextChoices):
        OPEN = "Open", "Open"
        IN_PROGRESS = "In Progress", "In Progress"
        COMPLETE = "Complete", "Complete"
        CANCELLED = "Cancelled", "Cancelled"

    class Priority(models.TextChoices):
        LOW = "Low", "Low"
        NORMAL = "Normal", "Normal"
        HIGH = "High", "High"
        URGENT = "Urgent", "Urgent"

    piano = models.ForeignKey(
        Piano, on_delete=models.PROTECT, related_name="work_orders"
    )
    assigned_tech = models.ForeignKey(
        Technician,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_orders",
    )
    service_visit = models.ForeignKey(
        ServiceVisit,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_orders",
    )
    schedule = models.ForeignKey(
        MaintenanceSchedule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_orders",
    )
    order_type = models.CharField(max_length=20, choices=OrderType.choices)
    task_type = models.CharField(
        max_length=20, choices=TaskType.choices, blank=True,
        help_text="Matches against piano maintenance schedule (Tuning, Regulation, etc.)",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.NORMAL
    )
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"WO-{self.pk} · {self.order_type} · {self.status}"


# ---------------------------------------------------------------------------
# MaintenanceLog
# ---------------------------------------------------------------------------
class MaintenanceLog(models.Model):
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.PROTECT, related_name="logs"
    )
    technician = models.ForeignKey(
        Technician, on_delete=models.PROTECT, related_name="logs"
    )
    piano = models.ForeignKey(
        Piano, on_delete=models.PROTECT, related_name="logs"
    )
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2)
    work_performed = models.TextField()
    notes = models.TextField(blank=True)
    logged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-logged_at"]

    def __str__(self):
        return f"Log #{self.pk} ({self.logged_at:%Y-%m-%d})"


# ---------------------------------------------------------------------------
# ConditionReading
# ---------------------------------------------------------------------------
class ConditionReading(models.Model):
    piano = models.ForeignKey(
        Piano, on_delete=models.PROTECT, related_name="condition_readings"
    )
    log = models.ForeignKey(
        MaintenanceLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="condition_readings",
    )

    # -- Environment readings -------------------------------------------------
    pitch_before_cents = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        db_column='pitch_before_cents',
    )
    pitch_after_cents = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    humidity_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    temperature_f = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    # -- Component conditions -------------------------------------------------
    regulation_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    voicing_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    belly_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    soundboard_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    pinblock_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    strings_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    hammers_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    keys_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    pedals_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    case_condition = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )

    overall_rating = models.CharField(
        max_length=30, choices=ConditionLevel.choices, blank=True
    )
    notes = models.TextField(blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)

    CONDITION_FIELDS = [
        'regulation_condition', 'voicing_condition', 'belly_condition',
        'soundboard_condition', 'pinblock_condition', 'strings_condition',
        'hammers_condition', 'keys_condition', 'pedals_condition',
        'case_condition',
    ]
    ENVIRONMENT_FIELDS = [
        ('pitch_after_cents', 'current_pitch'),
        ('humidity_pct', 'current_humidity'),
        ('temperature_f', 'current_temperature'),
    ]

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"Reading #{self.pk} ({self.recorded_at:%Y-%m-%d})"

    def update_piano_current_state(self):
        piano = self.piano
        for field in self.CONDITION_FIELDS:
            value = getattr(self, field)
            if value:
                setattr(piano, field, value)
        for reading_field, piano_field in self.ENVIRONMENT_FIELDS:
            value = getattr(self, reading_field)
            if value is not None:
                setattr(piano, piano_field, value)
        piano.save()


# ---------------------------------------------------------------------------
# Part
# ---------------------------------------------------------------------------
class Part(models.Model):
    name = models.CharField(max_length=200)
    part_number = models.CharField(max_length=100, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    unit_cost = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    stock_quantity = models.IntegerField(default=0)
    reorder_threshold = models.IntegerField(default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.part_number})" if self.part_number else self.name

    @property
    def needs_reorder(self):
        return self.stock_quantity <= self.reorder_threshold


# ---------------------------------------------------------------------------
# PartUsed
# ---------------------------------------------------------------------------
class PartUsed(models.Model):
    log = models.ForeignKey(
        MaintenanceLog, on_delete=models.PROTECT, related_name="parts_used"
    )
    part = models.ForeignKey(
        Part, on_delete=models.PROTECT, related_name="usages"
    )
    quantity_used = models.IntegerField()
    cost_at_time = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = "Part Used"
        verbose_name_plural = "Parts Used"

    def __str__(self):
        return f"{self.quantity_used}× Part #{self.part_id} (Log #{self.log_id})"


# ---------------------------------------------------------------------------
# MaintenanceRequest
# ---------------------------------------------------------------------------
class MaintenanceRequest(models.Model):
    class RequestStatus(models.TextChoices):
        NEW = "New", "New"
        ASSIGNED = "Assigned", "Assigned"
        RESOLVED = "Resolved", "Resolved"

    piano = models.ForeignKey(
        Piano, on_delete=models.PROTECT, related_name="maintenance_requests"
    )
    reported_by_name = models.CharField(max_length=200, blank=True)
    reported_by_email = models.EmailField(blank=True)
    issue_description = models.TextField()
    status = models.CharField(
        max_length=10,
        choices=RequestStatus.choices,
        default=RequestStatus.NEW,
    )
    work_order = models.ForeignKey(
        WorkOrder,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Request #{self.pk} · {self.status}"


# ---------------------------------------------------------------------------
# Photo
# ---------------------------------------------------------------------------
class Photo(models.Model):
    piano      = models.ForeignKey(Piano,     null=True, blank=True, on_delete=models.CASCADE, related_name='photos')
    work_order = models.ForeignKey(WorkOrder, null=True, blank=True, on_delete=models.CASCADE, related_name='photos')
    image      = models.ImageField(upload_to='photos/')
    caption    = models.CharField(max_length=300, blank=True)
    is_profile_photo = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        if self.piano_id:
            return f"Photo #{self.pk} (Piano #{self.piano_id})"
        if self.work_order_id:
            return f"Photo #{self.pk} (WO #{self.work_order_id})"
        return f"Photo #{self.pk}"


class Alert(models.Model):
    class AlertType(models.TextChoices):
        OVERDUE = "Overdue", "Overdue"
        DUE_SOON = "Due Soon", "Due Soon"

    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.CASCADE, related_name="alerts"
    )
    alert_type = models.CharField(max_length=20, choices=AlertType.choices)
    sent_at = models.DateTimeField(auto_now_add=True)
    acknowledged = models.BooleanField(default=False)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"Alert #{self.pk} · {self.alert_type} · WO-{self.work_order_id}"



class Attachment(models.Model):
    piano = models.ForeignKey(
        Piano,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    work_order = models.ForeignKey(
        WorkOrder,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to="attachments/%Y/%m/")
    filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.filename

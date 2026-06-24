import uuid
from datetime import date, timedelta
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator


def validate_image_file(value):
    """Reject uploads that aren't common image types or exceed 10 MB."""
    max_size = 10 * 1024 * 1024  # 10 MB
    if value.size > max_size:
        raise ValidationError(f'File too large — maximum is 10 MB (got {value.size / 1024 / 1024:.1f} MB).')
    allowed = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    if hasattr(value.file, 'content_type') and value.file.content_type not in allowed:
        raise ValidationError('Only JPEG, PNG, GIF, and WebP images are allowed.')

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


class Company(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name


class CompanyMembership(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        "Technician",
        on_delete=models.CASCADE,
        related_name="company_memberships",
    )
    role_admin = models.BooleanField(default=False)
    role_technician = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company__name", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "user"],
                name="unique_company_membership",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.company}"

    @property
    def role_display(self):
        if self.role_admin and self.role_technician:
            return "Admin + Technician"
        if self.role_admin:
            return "Admin"
        if self.role_technician:
            return "Technician"
        return "No Role"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.user.sync_role_flags()

    def delete(self, *args, **kwargs):
        user = self.user
        super().delete(*args, **kwargs)
        user.sync_role_flags()


class CompanyInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    email = models.EmailField()
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role_admin = models.BooleanField(default=False)
    role_technician = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        "Technician",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_company_invitations",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "email", "status"],
                condition=models.Q(status="pending"),
                name="unique_pending_invitation_per_company_email",
            ),
        ]

    def __str__(self):
        return f"Invite {self.email} to {self.company}"

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()


class AuditLog(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        "Technician",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    event_type = models.CharField(max_length=80)
    target_model = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company} · {self.event_type}"


# ---------------------------------------------------------------------------
# Organization  (administrative owner — who signs the contract)
# ---------------------------------------------------------------------------
class Tag(models.Model):
    """Free-form label that can be attached to pianos."""
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="tags",
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="unique_tag_name_per_company")
        ]

    def __str__(self):
        return self.name

class Organization(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="organizations",
    )
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

    def delete(self, *args, **kwargs):
        """Venues are SET_NULL; no extra stamping needed (venue still exists)."""
        super().delete(*args, **kwargs)


# ---------------------------------------------------------------------------
# Venue  (physical location a technician drives to)
# ---------------------------------------------------------------------------
class Venue(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="venues",
    )
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=50, blank=True)
    organization = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.SET_NULL, related_name="venues",
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

    def delete(self, *args, **kwargs):
        """Stamp display name into pianos before deletion."""
        self.pianos.update(venue_display=self.name)
        super().delete(*args, **kwargs)


# ---------------------------------------------------------------------------
# Piano
# ---------------------------------------------------------------------------
class Piano(models.Model):
    class PianoType(models.TextChoices):
        GRAND = "Grand", "Grand"
        UPRIGHT = "Upright", "Upright"
        DIGITAL = "Digital", "Digital"

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="pianos",
    )
    venue = models.ForeignKey(
        Venue, null=True, blank=True, on_delete=models.SET_NULL, related_name="pianos"
    )
    venue_display = models.CharField(max_length=200, blank=True,
        help_text="Preserved venue name after venue deletion.")
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
    def venue_name(self):
        """Return live venue name, or preserved display name if venue was deleted."""
        if self.venue:
            return self.venue.name
        return self.venue_display or "(deleted venue)"

    def _build_display_name(self):
        parts = [self.name]
        if self.make:
            parts.append(self.make)
        if self.serial_number:
            parts.append(f"SN-{self.serial_number}")
        return " — ".join(parts)

    def delete(self, *args, **kwargs):
        """Stamp display name into related objects before deletion."""
        display = self._build_display_name()
        self.work_orders.update(piano_display=display)
        self.logs.update(piano_display=display)
        self.condition_readings.update(piano_display=display)
        self.maintenance_requests.update(piano_display=display)
        super().delete(*args, **kwargs)

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
    role_admin = models.BooleanField(
        default=False,
        help_text="Can manage all settings, create/edit/delete records, and assign work.",
    )
    role_technician = models.BooleanField(
        default=True,
        help_text="Can be assigned work orders and log their own work.",
    )

    class Meta:
        verbose_name = "Technician"
        verbose_name_plural = "Technicians"

    def __str__(self):
        full = self.get_full_name()
        return full if full else self.username

    def sync_role_flags(self, save=True):
        memberships = self.company_memberships.filter(is_active=True)
        self.role_admin = memberships.filter(role_admin=True).exists()
        self.role_technician = memberships.filter(role_technician=True).exists()
        if save and self.pk:
            self.save(update_fields=["role_admin", "role_technician"])

    def active_company_memberships(self):
        return self.company_memberships.filter(
            is_active=True,
            company__is_active=True,
        ).select_related("company")

    def membership_for_company(self, company):
        if not self.pk or company is None:
            return None
        company_id = getattr(company, "pk", company)
        return self.active_company_memberships().filter(company_id=company_id).first()

    def has_company_role(self, company, *, admin=False, technician=False):
        membership = self.membership_for_company(company)
        if membership is None:
            return False
        if admin and not membership.role_admin:
            return False
        if technician and not membership.role_technician:
            return False
        return True

    @property
    def can_be_assigned(self):
        """Global derived flag; prefer can_be_assigned_in_company() for tenancy-aware checks."""
        return self.role_technician

    def can_be_assigned_in_company(self, company):
        return self.has_company_role(company, technician=True)

    @property
    def role_display(self):
        if self.role_admin and self.role_technician:
            return "Admin + Technician"
        elif self.role_admin:
            return "Admin"
        elif self.role_technician:
            return "Technician"
        return "No Role"



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
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="schedule_templates",
    )
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

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="maintenance_schedules",
    )
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

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="work_orders",
    )
    piano = models.ForeignKey(
        Piano, null=True, blank=True, on_delete=models.SET_NULL, related_name="work_orders"
    )
    piano_display = models.CharField(max_length=200, blank=True,
        help_text="Preserved piano name after piano deletion.")
    assigned_tech = models.ForeignKey(
        Technician,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_orders",
    )
    is_team_job = models.BooleanField(default=False, db_default=False)
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

    @property
    def piano_name(self):
        if self.piano:
            return self.piano.name
        return self.piano_display or "(deleted piano)"


# ---------------------------------------------------------------------------
# MaintenanceLog
# ---------------------------------------------------------------------------
class MaintenanceLog(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="maintenance_logs",
    )
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.CASCADE, related_name="logs"
    )
    technician = models.ForeignKey(
        Technician, on_delete=models.PROTECT, related_name="logs"
    )
    piano = models.ForeignKey(
        Piano, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs"
    )
    piano_display = models.CharField(max_length=200, blank=True,
        help_text="Preserved piano name after piano deletion.")
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
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="condition_readings",
    )
    piano = models.ForeignKey(
        Piano, null=True, blank=True, on_delete=models.SET_NULL, related_name="condition_readings"
    )
    piano_display = models.CharField(max_length=200, blank=True,
        help_text="Preserved piano name after piano deletion.")
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
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="parts",
    )
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
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="parts_used",
    )
    log = models.ForeignKey(
        MaintenanceLog, on_delete=models.CASCADE, related_name="parts_used"
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

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="maintenance_requests",
    )
    piano = models.ForeignKey(
        Piano, null=True, blank=True, on_delete=models.SET_NULL, related_name="maintenance_requests"
    )
    piano_display = models.CharField(max_length=200, blank=True,
        help_text="Preserved piano name after piano deletion.")
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
    company    = models.ForeignKey(Company,   on_delete=models.CASCADE, related_name='photos')
    piano      = models.ForeignKey(Piano,     null=True, blank=True, on_delete=models.CASCADE, related_name='photos')
    work_order = models.ForeignKey(WorkOrder, null=True, blank=True, on_delete=models.CASCADE, related_name='photos')
    image      = models.ImageField(upload_to='photos/%y/%m/%d/', validators=[validate_image_file])
    caption    = models.CharField(max_length=300, blank=True)
    is_profile_photo = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def clean(self):
        if not self.piano_id and not self.work_order_id:
            raise ValidationError('A photo must belong to a piano or a work order.')

        if self.piano_id and self.piano.company_id != self.company_id:
            raise ValidationError('Photo company must match the related piano company.')

        if self.work_order_id and self.work_order.company_id != self.company_id:
            raise ValidationError('Photo company must match the related work order company.')

        if self.piano_id and self.work_order_id:
            work_order_piano_id = self.work_order.piano_id
            if work_order_piano_id and work_order_piano_id != self.piano_id:
                raise ValidationError('Photo piano must match the related work order piano.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.piano_id:
            return f"Photo #{self.pk} (Piano #{self.piano_id})"
        if self.work_order_id:
            return f"Photo #{self.pk} (WO #{self.work_order_id})"
        return f"Photo #{self.pk}"

# ---------------------------------------------------------------------------
# Company Settings (singleton)
# ---------------------------------------------------------------------------
class CompanySettings(models.Model):
    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    company_name = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    default_labor_rate = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        help_text="Default hourly labor rate for cost calculations.",
    )

    class Meta:
        verbose_name = "Company Settings"
        verbose_name_plural = "Company Settings"

    def __str__(self):
        return self.company_name or "Company Settings"

    @classmethod
    def load_for_company(cls, company):
        obj, _ = cls.objects.get_or_create(company=company)
        return obj

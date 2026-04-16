import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------
class Location(models.Model):
    name = models.CharField(max_length=200)
    building = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

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

    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="pianos"
    )
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    piano_type = models.CharField(max_length=20, choices=PianoType.choices)
    date_acquired = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    qr_code_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        ordering = ["location", "name"]

    def __str__(self):
        return f"{self.brand} {self.model} — {self.name}".strip(" —")


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

    class Meta:
        verbose_name = "Technician"
        verbose_name_plural = "Technicians"

    def __str__(self):
        full = self.get_full_name()
        return full if full else self.username


# ---------------------------------------------------------------------------
# MaintenanceSchedule
# ---------------------------------------------------------------------------
class MaintenanceSchedule(models.Model):
    class TaskType(models.TextChoices):
        TUNING = "Tuning", "Tuning"
        REGULATION = "Regulation", "Regulation"
        VOICING = "Voicing", "Voicing"
        CLEANING = "Cleaning", "Cleaning"
        INSPECTION = "Inspection", "Inspection"
        OTHER = "Other", "Other"

    piano = models.ForeignKey(
        Piano, on_delete=models.CASCADE, related_name="schedules"
    )
    task_name = models.CharField(max_length=200)
    task_type = models.CharField(max_length=20, choices=TaskType.choices)
    interval_days = models.IntegerField()
    warning_days_before = models.IntegerField(default=7)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["piano", "task_type"]

    def __str__(self):
        return f"{self.piano} — {self.task_name} (every {self.interval_days}d)"


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
    schedule = models.ForeignKey(
        MaintenanceSchedule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_orders",
    )
    order_type = models.CharField(max_length=20, choices=OrderType.choices)
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
        return f"WO-{self.pk} | {self.piano} | {self.status}"


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
        return f"Log {self.pk} — {self.piano} by {self.technician}"


# ---------------------------------------------------------------------------
# ConditionReading
# ---------------------------------------------------------------------------
class ConditionReading(models.Model):
    class OverallRating(models.TextChoices):
        POOR = "Poor", "Poor"
        FAIR = "Fair", "Fair"
        GOOD = "Good", "Good"
        EXCELLENT = "Excellent", "Excellent"

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
    pitch_offset_cents = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    humidity_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    temperature_f = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    overall_rating = models.CharField(
        max_length=10, choices=OverallRating.choices, blank=True
    )
    notes = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"Reading {self.pk} — {self.piano} @ {self.recorded_at:%Y-%m-%d}"


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
        return f"{self.quantity_used}x {self.part} (Log {self.log_id})"


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
        return f"Request {self.pk} — {self.piano} [{self.status}]"

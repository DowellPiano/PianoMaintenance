import uuid
import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # Technician (custom user — must come before any FK references)
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Technician",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last login"
                    ),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        error_messages={
                            "unique": "A user with that username already exists."
                        },
                        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
                        max_length=150,
                        unique=True,
                        validators=[
                            django.contrib.auth.validators.UnicodeUsernameValidator()
                        ],
                        verbose_name="username",
                    ),
                ),
                (
                    "first_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="first name"
                    ),
                ),
                (
                    "last_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="last name"
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        blank=True, max_length=254, verbose_name="email address"
                    ),
                ),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into this admin site.",
                        verbose_name="staff status",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True),
                ),
                (
                    "date_joined",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="date joined"
                    ),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "Technician",
                "verbose_name_plural": "Technicians",
            },
            managers=[
                ("objects", django.contrib.auth.models.UserManager()),
            ],
        ),
        # ------------------------------------------------------------------
        # Location
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Location",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("building", models.CharField(blank=True, max_length=200)),
                ("address", models.TextField(blank=True)),
            ],
            options={"ordering": ["name"]},
        ),
        # ------------------------------------------------------------------
        # Piano
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Piano",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pianos",
                        to="maintenance.location",
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("brand", models.CharField(max_length=100)),
                ("model", models.CharField(blank=True, max_length=100)),
                ("serial_number", models.CharField(blank=True, max_length=100)),
                (
                    "piano_type",
                    models.CharField(
                        choices=[
                            ("Grand", "Grand"),
                            ("Upright", "Upright"),
                            ("Digital", "Digital"),
                        ],
                        max_length=20,
                    ),
                ),
                ("date_acquired", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                (
                    "qr_code_token",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
            ],
            options={"ordering": ["location", "name"]},
        ),
        # ------------------------------------------------------------------
        # MaintenanceSchedule
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="MaintenanceSchedule",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "piano",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schedules",
                        to="maintenance.piano",
                    ),
                ),
                ("task_name", models.CharField(max_length=200)),
                (
                    "task_type",
                    models.CharField(
                        choices=[
                            ("Tuning", "Tuning"),
                            ("Regulation", "Regulation"),
                            ("Voicing", "Voicing"),
                            ("Cleaning", "Cleaning"),
                            ("Inspection", "Inspection"),
                            ("Other", "Other"),
                        ],
                        max_length=20,
                    ),
                ),
                ("interval_days", models.IntegerField()),
                ("warning_days_before", models.IntegerField(default=7)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["piano", "task_type"]},
        ),
        # ------------------------------------------------------------------
        # WorkOrder
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="WorkOrder",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "piano",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="work_orders",
                        to="maintenance.piano",
                    ),
                ),
                (
                    "assigned_tech",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="work_orders",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "schedule",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="work_orders",
                        to="maintenance.maintenanceschedule",
                    ),
                ),
                (
                    "order_type",
                    models.CharField(
                        choices=[
                            ("Preventive", "Preventive"),
                            ("Request", "Request"),
                            ("Emergency", "Emergency"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("Open", "Open"),
                            ("In Progress", "In Progress"),
                            ("Complete", "Complete"),
                            ("Cancelled", "Cancelled"),
                        ],
                        default="Open",
                        max_length=20,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[
                            ("Low", "Low"),
                            ("Normal", "Normal"),
                            ("High", "High"),
                            ("Urgent", "Urgent"),
                        ],
                        default="Normal",
                        max_length=10,
                    ),
                ),
                ("description", models.TextField(blank=True)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("completed_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        # ------------------------------------------------------------------
        # MaintenanceLog
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="MaintenanceLog",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "work_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="logs",
                        to="maintenance.workorder",
                    ),
                ),
                (
                    "technician",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "piano",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="logs",
                        to="maintenance.piano",
                    ),
                ),
                (
                    "hours_worked",
                    models.DecimalField(decimal_places=2, max_digits=5),
                ),
                ("work_performed", models.TextField()),
                ("notes", models.TextField(blank=True)),
                ("logged_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-logged_at"]},
        ),
        # ------------------------------------------------------------------
        # ConditionReading
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="ConditionReading",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "piano",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="condition_readings",
                        to="maintenance.piano",
                    ),
                ),
                (
                    "log",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="condition_readings",
                        to="maintenance.maintenancelog",
                    ),
                ),
                (
                    "pitch_offset_cents",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=6, null=True
                    ),
                ),
                (
                    "humidity_pct",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=5, null=True
                    ),
                ),
                (
                    "temperature_f",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=5, null=True
                    ),
                ),
                (
                    "overall_rating",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("Poor", "Poor"),
                            ("Fair", "Fair"),
                            ("Good", "Good"),
                            ("Excellent", "Excellent"),
                        ],
                        max_length=10,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-recorded_at"]},
        ),
        # ------------------------------------------------------------------
        # Part
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Part",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("part_number", models.CharField(blank=True, max_length=100)),
                ("supplier", models.CharField(blank=True, max_length=200)),
                (
                    "unit_cost",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=8, null=True
                    ),
                ),
                ("stock_quantity", models.IntegerField(default=0)),
                ("reorder_threshold", models.IntegerField(default=0)),
            ],
            options={"ordering": ["name"]},
        ),
        # ------------------------------------------------------------------
        # PartUsed
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="PartUsed",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "log",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="parts_used",
                        to="maintenance.maintenancelog",
                    ),
                ),
                (
                    "part",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="usages",
                        to="maintenance.part",
                    ),
                ),
                ("quantity_used", models.IntegerField()),
                (
                    "cost_at_time",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=8, null=True
                    ),
                ),
            ],
            options={
                "verbose_name": "Part Used",
                "verbose_name_plural": "Parts Used",
            },
        ),
        # ------------------------------------------------------------------
        # MaintenanceRequest
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="MaintenanceRequest",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "piano",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="maintenance_requests",
                        to="maintenance.piano",
                    ),
                ),
                ("reported_by_name", models.CharField(blank=True, max_length=200)),
                ("reported_by_email", models.EmailField(blank=True)),
                ("issue_description", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("New", "New"),
                            ("Assigned", "Assigned"),
                            ("Resolved", "Resolved"),
                        ],
                        default="New",
                        max_length=10,
                    ),
                ),
                (
                    "work_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="maintenance_requests",
                        to="maintenance.workorder",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]

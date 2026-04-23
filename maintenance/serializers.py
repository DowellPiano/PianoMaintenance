from rest_framework import serializers
from .models import (
    Attachment,
    Location,
    MaintenanceLog,
    MaintenanceSchedule,
    Piano,
    ScheduleTemplate,
    Technician,
    WorkOrder,
)


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------
class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['id', 'name', 'building', 'address']


# ---------------------------------------------------------------------------
# Piano
# ---------------------------------------------------------------------------
class PianoSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = Piano
        fields = [
            'id',
            'name',
            'brand',
            'model',
            'serial_number',
            'piano_type',
            'location',
            'location_name',
            'date_acquired',
            'notes',
            'qr_code_token',
        ]
        read_only_fields = ['qr_code_token']


# ---------------------------------------------------------------------------
# Technician
# ---------------------------------------------------------------------------
class TechnicianSerializer(serializers.ModelSerializer):
    class Meta:
        model = Technician
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'is_active',
            'date_joined',
        ]
        read_only_fields = ['is_active', 'date_joined']


# ---------------------------------------------------------------------------
# ScheduleTemplate
# ---------------------------------------------------------------------------
class ScheduleTemplateSerializer(serializers.ModelSerializer):
    schedule_count = serializers.IntegerField(source='schedules.count', read_only=True)

    class Meta:
        model = ScheduleTemplate
        fields = [
            'id',
            'name',
            'task_name',
            'task_type',
            'interval_days',
            'warning_days_before',
            'description',
            'schedule_count',
        ]


# ---------------------------------------------------------------------------
# MaintenanceSchedule
# ---------------------------------------------------------------------------
class MaintenanceScheduleSerializer(serializers.ModelSerializer):
    piano_name = serializers.CharField(source='piano.name', read_only=True)
    piano_brand = serializers.CharField(source='piano.brand', read_only=True)
    piano_location = serializers.CharField(source='piano.location.name', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)

    class Meta:
        model = MaintenanceSchedule
        fields = [
            'id',
            'piano',
            'piano_name',
            'piano_brand',
            'piano_location',
            'template',
            'template_name',
            'task_name',
            'task_type',
            'interval_days',
            'warning_days_before',
            'is_active',
            'last_service_date',
        ]


# ---------------------------------------------------------------------------
# WorkOrder
# ---------------------------------------------------------------------------
class WorkOrderSerializer(serializers.ModelSerializer):
    piano_name = serializers.SerializerMethodField(read_only=True)
    assigned_tech_name = serializers.SerializerMethodField(read_only=True)

    def get_piano_name(self, obj):
        return str(obj.piano) if obj.piano_id else None

    def get_assigned_tech_name(self, obj):
        if obj.assigned_tech:
            return obj.assigned_tech.get_full_name() or obj.assigned_tech.username
        return None

    class Meta:
        model = WorkOrder
        fields = [
            'id',
            'piano',
            'piano_name',
            'assigned_tech',
            'assigned_tech_name',
            'schedule',
            'order_type',
            'status',
            'priority',
            'description',
            'due_date',
            'completed_date',
            'created_at',
        ]
        read_only_fields = ['status', 'completed_date', 'created_at']


# ---------------------------------------------------------------------------
# MaintenanceLog
# ---------------------------------------------------------------------------
class MaintenanceLogSerializer(serializers.ModelSerializer):
    technician_name = serializers.SerializerMethodField(read_only=True)
    piano_name = serializers.SerializerMethodField(read_only=True)

    def get_technician_name(self, obj):
        if obj.technician:
            return obj.technician.get_full_name() or obj.technician.username
        return None

    def get_piano_name(self, obj):
        return str(obj.piano) if obj.piano_id else None

    class Meta:
        model = MaintenanceLog
        fields = [
            'id',
            'work_order',
            'technician',
            'technician_name',
            'piano',
            'piano_name',
            'hours_worked',
            'work_performed',
            'notes',
            'logged_at',
        ]
        read_only_fields = ['logged_at']


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------
class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = [
            'id',
            'piano',
            'work_order',
            'file',
            'filename',
            'uploaded_at',
        ]
        read_only_fields = ['uploaded_at']

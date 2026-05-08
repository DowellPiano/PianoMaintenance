from datetime import date, timedelta
from rest_framework import serializers
from .models import (
    Attachment,
    ConditionReading,
    Organization,
    Venue,
    MaintenanceLog,
    MaintenanceSchedule,
    Piano,
    ScheduleTemplate,
    Technician,
    Team,
    Photo,
    WorkOrder,
    Part,
    PartUsed,
    MaintenanceRequest,
    Alert,
)


class OrganizationSerializer(serializers.ModelSerializer):
    venue_count = serializers.IntegerField(source='venues.count', read_only=True)

    class Meta:
        model = Organization
        fields = ['id', 'name', 'short_name', 'address',
                  'contact_name', 'contact_email', 'contact_phone',
                  'notes', 'venue_count']


class VenueSerializer(serializers.ModelSerializer):
    piano_count = serializers.IntegerField(source='pianos.count', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = Venue
        fields = ['id', 'name', 'short_name', 'organization', 'organization_name',
                  'address', 'on_site_contact', 'parking_notes', 'access_notes',
                  'notes', 'piano_count']


class PhotoSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Photo
        fields = ['id', 'piano', 'work_order', 'image', 'image_url', 'caption', 'is_profile_photo', 'uploaded_at']
        read_only_fields = ['uploaded_at']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class PianoSerializer(serializers.ModelSerializer):
    venue_name = serializers.CharField(source='venue.name', read_only=True)
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Piano
        fields = [
            'id', 'name', 'make', 'model', 'serial_number',
            'piano_type', 'venue', 'venue_name',
            'year_built', 'year_acquired', 'notes', 'is_active', 'qr_code_token',
            'profile_photo_url',
        ]
        read_only_fields = ['qr_code_token']

    def get_profile_photo_url(self, obj):
        request = self.context.get('request')
        photo = obj.photos.filter(is_profile_photo=True).first()
        if photo and photo.image and request:
            return request.build_absolute_uri(photo.image.url)
        return None


class ScheduleTemplateSerializer(serializers.ModelSerializer):
    schedule_count = serializers.IntegerField(source='schedules.count', read_only=True)

    class Meta:
        model = ScheduleTemplate
        fields = [
            'id', 'name', 'task_name', 'task_type',
            'interval_days', 'warning_days_before', 'description', 'schedule_count',
        ]


class MaintenanceScheduleSerializer(serializers.ModelSerializer):
    piano_name = serializers.CharField(source='piano.name', read_only=True)
    piano_make = serializers.CharField(source='piano.make', read_only=True)
    piano_location = serializers.CharField(source='piano.venue.name', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)
    next_due = serializers.SerializerMethodField()

    def get_next_due(self, obj):
        today = date.today()
        last = (
            WorkOrder.objects
            .filter(schedule=obj, status=WorkOrder.Status.COMPLETE, completed_date__isnull=False)
            .order_by('-completed_date')
            .values_list('completed_date', flat=True)
            .first()
        )
        anchor = last if last else (today - timedelta(days=obj.interval_days))
        return str(anchor + timedelta(days=obj.interval_days))

    class Meta:
        model = MaintenanceSchedule
        fields = [
            'id', 'piano', 'piano_name', 'piano_make', 'piano_location',
            'template', 'template_name', 'task_name', 'task_type',
            'interval_days', 'warning_days_before', 'is_active',
            'last_service_date', 'next_due',
        ]


class TechnicianMinimalSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    team_name = serializers.SerializerMethodField()

    class Meta:
        model = Technician
        fields = [
            'id', 'username', 'full_name', 'first_name', 'last_name',
            'email', 'is_active', 'is_staff', 'date_joined',
            'team', 'team_name',
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_team_name(self, obj):
        return obj.team.name if obj.team_id else None


class MaintenanceLogSerializer(serializers.ModelSerializer):
    technician_name = serializers.SerializerMethodField(read_only=True)
    piano = serializers.PrimaryKeyRelatedField(source='work_order.piano', read_only=True)
    piano_name = serializers.CharField(source='work_order.piano.name', read_only=True)

    class Meta:
        model = MaintenanceLog
        fields = [
            'id', 'work_order', 'technician', 'technician_name',
            'piano', 'piano_name',
            'hours_worked', 'work_performed', 'notes', 'logged_at',
        ]
        read_only_fields = ['logged_at']

    def get_technician_name(self, obj):
        return obj.technician.get_full_name() or obj.technician.username


class WorkOrderSerializer(serializers.ModelSerializer):
    piano_name = serializers.CharField(source='piano.name', read_only=True)
    piano_make = serializers.CharField(source='piano.make', read_only=True)
    piano_location = serializers.CharField(source='piano.venue.name', read_only=True)
    assigned_tech_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = WorkOrder
        fields = [
            'id', 'piano', 'piano_name', 'piano_make', 'piano_location',
            'assigned_tech', 'assigned_tech_name', 'schedule',
            'order_type', 'status', 'priority',
            'description', 'due_date', 'completed_date', 'created_at',
        ]
        read_only_fields = ['created_at']

    def get_assigned_tech_name(self, obj):
        if obj.assigned_tech:
            return obj.assigned_tech.get_full_name() or obj.assigned_tech.username
        return None


class ConditionReadingSerializer(serializers.ModelSerializer):
    piano_name = serializers.CharField(source='piano.name', read_only=True)

    class Meta:
        model = ConditionReading
        fields = [
            'id', 'piano', 'piano_name', 'log',
            'pitch_before_cents', 'pitch_after_cents', 'humidity_pct', 'temperature_f',
            'regulation_condition', 'voicing_condition', 'belly_condition',
            'soundboard_condition', 'pinblock_condition', 'strings_condition',
            'hammers_condition', 'keys_condition', 'pedals_condition', 'case_condition',
            'overall_rating', 'notes', 'recorded_at',
        ]


class PartSerializer(serializers.ModelSerializer):
    needs_reorder = serializers.BooleanField(read_only=True)

    class Meta:
        model = Part
        fields = [
            'id', 'name', 'part_number', 'supplier',
            'unit_cost', 'stock_quantity', 'reorder_threshold', 'needs_reorder',
        ]


class PartUsedSerializer(serializers.ModelSerializer):
    part_name = serializers.CharField(source='part.name', read_only=True)

    class Meta:
        model = PartUsed
        fields = ['id', 'log', 'part', 'part_name', 'quantity_used', 'cost_at_time']


class TechnicianSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    full_name = serializers.SerializerMethodField(read_only=True)
    team_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Technician
        fields = [
            'id', 'username', 'full_name', 'email', 'first_name', 'last_name',
            'is_active', 'is_staff', 'date_joined', 'password',
            'team', 'team_name',
        ]
        read_only_fields = ['date_joined']

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_team_name(self, obj):
        return obj.team.name if obj.team_id else None

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = Technician(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        validated_data.pop('username', None)
        validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class TeamSerializer(serializers.ModelSerializer):
    manager_name = serializers.SerializerMethodField(read_only=True)
    member_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Team
        fields = ['id', 'name', 'manager', 'manager_name', 'member_count']

    def get_manager_name(self, obj):
        if obj.manager:
            return obj.manager.get_full_name() or obj.manager.username
        return None

    def get_member_count(self, obj):
        return obj.members.count()


class MaintenanceRequestSerializer(serializers.ModelSerializer):
    piano_name = serializers.CharField(source='piano.name', read_only=True)
    piano_location = serializers.CharField(source='piano.venue.name', read_only=True)
    wo_assigned_tech = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceRequest
        fields = [
            'id', 'piano', 'piano_name', 'piano_location',
            'reported_by_name', 'reported_by_email',
            'issue_description', 'status', 'work_order',
            'wo_assigned_tech', 'created_at',
        ]
        read_only_fields = ['created_at']

    def get_wo_assigned_tech(self, obj):
        if obj.work_order and obj.work_order.assigned_tech:
            return obj.work_order.assigned_tech.get_full_name() or obj.work_order.assigned_tech.username
        return None


class AlertSerializer(serializers.ModelSerializer):
    piano_name = serializers.CharField(source='work_order.piano.name', read_only=True)
    piano_location = serializers.CharField(source='work_order.piano.venue.name', read_only=True)
    due_date = serializers.DateField(source='work_order.due_date', read_only=True)
    priority = serializers.CharField(source='work_order.priority', read_only=True)

    class Meta:
        model = Alert
        fields = [
            'id', 'work_order', 'alert_type', 'sent_at', 'acknowledged',
            'piano_name', 'piano_location', 'due_date', 'priority',
        ]
        read_only_fields = ['sent_at']


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = [
            'id', 'piano', 'work_order', 'file', 'filename', 'uploaded_at',
        ]
        read_only_fields = ['uploaded_at']

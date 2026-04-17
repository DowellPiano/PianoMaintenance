from rest_framework import serializers
from .models import Location, Piano, MaintenanceSchedule, ScheduleTemplate, WorkOrder, Technician, Photo


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['id', 'name', 'building', 'address']


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
    location_name     = serializers.CharField(source='location.name', read_only=True)
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Piano
        fields = [
            'id', 'name', 'brand', 'model', 'serial_number',
            'piano_type', 'location', 'location_name',
            'date_acquired', 'notes', 'qr_code_token',
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
    piano_name     = serializers.CharField(source='piano.name',          read_only=True)
    piano_brand    = serializers.CharField(source='piano.brand',         read_only=True)
    piano_location = serializers.CharField(source='piano.location.name', read_only=True)
    template_name  = serializers.CharField(source='template.name',       read_only=True)

    class Meta:
        model = MaintenanceSchedule
        fields = [
            'id', 'piano', 'piano_name', 'piano_brand', 'piano_location',
            'template', 'template_name', 'task_name', 'task_type',
            'interval_days', 'warning_days_before', 'is_active',
        ]


class TechnicianMinimalSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Technician
        fields = ['id', 'username', 'full_name']

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class WorkOrderSerializer(serializers.ModelSerializer):
    piano_name          = serializers.CharField(source='piano.name',          read_only=True)
    piano_brand         = serializers.CharField(source='piano.brand',         read_only=True)
    piano_location      = serializers.CharField(source='piano.location.name', read_only=True)
    assigned_tech_name  = serializers.CharField(source='assigned_tech.get_full_name', read_only=True)

    class Meta:
        model = WorkOrder
        fields = [
            'id', 'piano', 'piano_name', 'piano_brand', 'piano_location',
            'assigned_tech', 'assigned_tech_name', 'schedule',
            'order_type', 'status', 'priority',
            'description', 'due_date', 'completed_date', 'created_at',
        ]
        read_only_fields = ['created_at']

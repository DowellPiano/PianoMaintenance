from rest_framework import serializers
from .models import Location, Piano, MaintenanceSchedule, ScheduleTemplate


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['id', 'name', 'building', 'address']


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
        ]

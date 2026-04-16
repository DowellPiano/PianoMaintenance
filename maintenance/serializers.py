from rest_framework import serializers
from .models import Location, Piano


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

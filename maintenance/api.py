from rest_framework import viewsets
from .models import Location, Piano
from .serializers import LocationSerializer, PianoSerializer


class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Location.objects.all().order_by('name')
    serializer_class = LocationSerializer


class PianoViewSet(viewsets.ModelViewSet):
    queryset = Piano.objects.select_related('location').order_by('location__name', 'name')
    serializer_class = PianoSerializer

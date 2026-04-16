from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Location, Piano, MaintenanceSchedule, ScheduleTemplate
from .serializers import (
    LocationSerializer,
    PianoSerializer,
    MaintenanceScheduleSerializer,
    ScheduleTemplateSerializer,
)


class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Location.objects.all().order_by('name')
    serializer_class = LocationSerializer


class PianoViewSet(viewsets.ModelViewSet):
    queryset = Piano.objects.select_related('location').order_by('location__name', 'name')
    serializer_class = PianoSerializer


class ScheduleTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduleTemplateSerializer

    def get_queryset(self):
        return ScheduleTemplate.objects.prefetch_related('schedules').order_by('name')

    @action(detail=True, methods=['post'])
    def apply_to_pianos(self, request, pk=None):
        template = self.get_object()
        piano_ids = request.data.get('piano_ids', [])
        if not piano_ids:
            return Response({'error': 'No pianos selected.'}, status=status.HTTP_400_BAD_REQUEST)

        pianos = Piano.objects.filter(id__in=piano_ids)
        created = []
        for piano in pianos:
            schedule = MaintenanceSchedule.objects.create(
                piano=piano,
                template=template,
                task_name=template.task_name,
                task_type=template.task_type,
                interval_days=template.interval_days,
                warning_days_before=template.warning_days_before,
            )
            created.append(schedule.id)

        return Response({'created': len(created), 'schedule_ids': created})


class MaintenanceScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceScheduleSerializer

    def get_queryset(self):
        return MaintenanceSchedule.objects.select_related(
            'piano__location', 'template'
        ).order_by('piano__location__name', 'piano__name', 'task_type')

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    LocationViewSet,
    PianoViewSet,
    MaintenanceScheduleViewSet,
    ScheduleTemplateViewSet,
    WorkOrderViewSet,
    TechnicianViewSet,
    PhotoViewSet,
    calendar_events,
    piano_profile,
    location_profile,
)

router = DefaultRouter()
router.register(r'locations',          LocationViewSet,            basename='location')
router.register(r'pianos',             PianoViewSet)
router.register(r'schedules',          MaintenanceScheduleViewSet, basename='schedule')
router.register(r'schedule-templates', ScheduleTemplateViewSet,    basename='schedule-template')
router.register(r'work-orders',        WorkOrderViewSet,           basename='work-order')
router.register(r'technicians',        TechnicianViewSet,          basename='technician')
router.register(r'photos',             PhotoViewSet,               basename='photo')

urlpatterns = [
    path('', include(router.urls)),
    path('calendar-events/', calendar_events, name='calendar-events'),
    path('pianos/<int:piano_id>/profile/',       piano_profile,    name='piano-profile'),
    path('locations/<int:location_id>/profile/', location_profile, name='location-profile'),
]

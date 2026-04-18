from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    LocationViewSet,
    PianoViewSet,
    MaintenanceScheduleViewSet,
    ScheduleTemplateViewSet,
    WorkOrderViewSet,
    TechnicianViewSet,
    calendar_events,
)

router = DefaultRouter()
router.register(r'locations',          LocationViewSet)
router.register(r'pianos',             PianoViewSet)
router.register(r'schedules',          MaintenanceScheduleViewSet, basename='schedule')
router.register(r'schedule-templates', ScheduleTemplateViewSet,    basename='schedule-template')
router.register(r'work-orders',        WorkOrderViewSet,           basename='work-order')
router.register(r'technicians',        TechnicianViewSet,          basename='technician')

urlpatterns = [
    path('', include(router.urls)),
    path('calendar-events/', calendar_events, name='calendar-events'),
]

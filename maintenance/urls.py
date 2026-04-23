from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    AttachmentViewSet,
    LocationViewSet,
    MaintenanceScheduleViewSet,
    PianoViewSet,
    ReportsViewSet,
    ScheduleTemplateViewSet,
    TechnicianViewSet,
    WorkOrderViewSet,
)

router = DefaultRouter()
router.register(r'locations',         LocationViewSet,          basename='location')
router.register(r'pianos',            PianoViewSet,             basename='piano')
router.register(r'technicians',       TechnicianViewSet,        basename='technician')
router.register(r'schedules',         MaintenanceScheduleViewSet, basename='schedule')
router.register(r'schedule-templates', ScheduleTemplateViewSet,  basename='schedule-template')
router.register(r'work-orders',       WorkOrderViewSet,         basename='work-order')
router.register(r'attachments',       AttachmentViewSet,        basename='attachment')
router.register(r'reports',           ReportsViewSet,           basename='report')

urlpatterns = [
    path('', include(router.urls)),
]

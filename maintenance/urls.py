from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import LocationViewSet, PianoViewSet, MaintenanceScheduleViewSet, ScheduleTemplateViewSet

router = DefaultRouter()
router.register(r'locations', LocationViewSet)
router.register(r'pianos', PianoViewSet)
router.register(r'schedules', MaintenanceScheduleViewSet, basename='schedule')
router.register(r'schedule-templates', ScheduleTemplateViewSet, basename='schedule-template')

urlpatterns = [
    path('', include(router.urls)),
]

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    LocationViewSet,
    PianoViewSet,
    MaintenanceScheduleViewSet,
    ScheduleTemplateViewSet,
    WorkOrderViewSet,
    MaintenanceLogViewSet,
    TechnicianViewSet,
    TeamViewSet,
    PhotoViewSet,
    ConditionReadingViewSet,
    PartViewSet,
    PartUsedViewSet,
    MaintenanceRequestViewSet,
    dashboard_stats,
    calendar_events,
    piano_profile,
    location_profile,
    auth_login,
    auth_logout,
    auth_me,
)

router = DefaultRouter()
router.register(r'locations',          LocationViewSet,            basename='location')
router.register(r'pianos',             PianoViewSet)
router.register(r'schedules',          MaintenanceScheduleViewSet, basename='schedule')
router.register(r'schedule-templates', ScheduleTemplateViewSet,    basename='schedule-template')
router.register(r'work-orders',        WorkOrderViewSet,           basename='work-order')
router.register(r'technicians',        TechnicianViewSet,          basename='technician')
router.register(r'teams',              TeamViewSet,                basename='team')
router.register(r'photos',             PhotoViewSet,               basename='photo')
router.register(r'maintenance-logs',   MaintenanceLogViewSet,      basename='maintenance-log')
router.register(r'condition-readings', ConditionReadingViewSet,    basename='condition-reading')
router.register(r'parts',             PartViewSet,                 basename='part')
router.register(r'parts-used',        PartUsedViewSet,             basename='parts-used')
router.register(r'maintenance-requests', MaintenanceRequestViewSet, basename='maintenance-request')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', dashboard_stats, name='dashboard-stats'),
    path('calendar-events/', calendar_events, name='calendar-events'),
    path('pianos/<int:piano_id>/profile/',       piano_profile,    name='piano-profile'),
    path('locations/<int:location_id>/profile/', location_profile, name='location-profile'),
    # Auth
    path('auth/login/',  auth_login,  name='auth-login'),
    path('auth/logout/', auth_logout, name='auth-logout'),
    path('auth/me/',     auth_me,     name='auth-me'),
]

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    AttachmentViewSet,
    ConditionReadingViewSet,
    OrganizationViewSet,
    VenueViewSet,
    MaintenanceScheduleViewSet,
    MaintenanceLogViewSet,
    PianoViewSet,
    ReportsViewSet,
    ScheduleTemplateViewSet,
    TechnicianViewSet,
    TeamViewSet,
    PhotoViewSet,
    WorkOrderViewSet,
    PartViewSet,
    PartUsedViewSet,
    MaintenanceRequestViewSet,
    AlertViewSet,
    alert_unread_count,
    dashboard_stats,
    calendar_events,
    piano_profile,
    venue_profile,
    auth_login,
    auth_logout,
    auth_me,
)

router = DefaultRouter()
router.register(r'organizations',       OrganizationViewSet,        basename='organization')
router.register(r'venues',              VenueViewSet,               basename='venue')
router.register(r'pianos',              PianoViewSet,               basename='piano')
router.register(r'technicians',         TechnicianViewSet,          basename='technician')
router.register(r'teams',               TeamViewSet,                basename='team')
router.register(r'schedules',           MaintenanceScheduleViewSet, basename='schedule')
router.register(r'schedule-templates',  ScheduleTemplateViewSet,    basename='schedule-template')
router.register(r'work-orders',         WorkOrderViewSet,           basename='work-order')
router.register(r'maintenance-logs',    MaintenanceLogViewSet,      basename='maintenance-log')
router.register(r'condition-readings',  ConditionReadingViewSet,    basename='condition-reading')
router.register(r'attachments',         AttachmentViewSet,          basename='attachment')
router.register(r'photos',              PhotoViewSet,               basename='photo')
router.register(r'parts',              PartViewSet,                 basename='part')
router.register(r'parts-used',         PartUsedViewSet,             basename='parts-used')
router.register(r'maintenance-requests', MaintenanceRequestViewSet, basename='maintenance-request')
router.register(r'alerts',              AlertViewSet,               basename='alert')
router.register(r'reports',             ReportsViewSet,             basename='report')

urlpatterns = [
    # Fixed paths BEFORE router.urls so they are not swallowed by /<id>/ detail routes
    path('alerts/unread-count/', alert_unread_count, name='alert-unread-count'),
    path('', include(router.urls)),
    path('dashboard/', dashboard_stats, name='dashboard-stats'),
    path('calendar-events/', calendar_events, name='calendar-events'),
    path('pianos/<int:piano_id>/profile/',   piano_profile, name='piano-profile'),
    path('venues/<int:venue_id>/profile/',   venue_profile, name='venue-profile'),
    # Auth
    path('auth/login/',  auth_login,  name='auth-login'),
    path('auth/logout/', auth_logout, name='auth-logout'),
    path('auth/me/',     auth_me,     name='auth-me'),
]

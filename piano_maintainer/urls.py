from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from maintenance import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('maintenance.urls')),

    # Auth
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # Template views
    path('', views.dashboard, name='dashboard'),

    # Pianos
    path('pianos/', views.piano_list, name='piano_list'),
    path('pianos/new/', views.piano_create, name='piano_create'),
    path('pianos/import/', views.piano_import_csv, name='piano_import'),
    path('pianos/qr-codes/', views.qr_codes, name='qr_codes'),
    path('pianos/<int:pk>/', views.piano_detail, name='piano_detail'),
    path('pianos/<int:pk>/edit/', views.piano_edit, name='piano_edit'),
    path('pianos/<int:pk>/tab/<str:tab>/', views.piano_tab, name='piano_tab'),
    path('pianos/<int:piano_pk>/condition/new/', views.condition_reading_create, name='condition_reading_create'),
    path('pianos/<int:pk>/photos/upload/', views.piano_photo_upload, name='piano_photo_upload'),
    path('pianos/<int:pk>/photos/<int:photo_pk>/set-profile/', views.piano_set_profile_photo, name='piano_set_profile_photo'),

    # Locations
    path('locations/', views.location_list, name='location_list'),
    path('locations/<int:pk>/', views.location_detail, name='location_detail'),

    # Work Orders
    path('work-orders/', views.workorder_list, name='workorder_list'),
    path('work-orders/new/', views.workorder_create, name='workorder_create'),
    path('work-orders/<int:pk>/', views.workorder_detail, name='workorder_detail'),
    path('work-orders/<int:pk>/assign/', views.workorder_assign, name='workorder_assign'),
    path('work-orders/<int:pk>/complete/', views.workorder_complete, name='workorder_complete'),

    # Schedule
    path('schedule/', views.schedule, name='schedule'),

    # Requests
    path('requests/', views.request_list, name='request_list'),
    path('requests/<int:pk>/approve/', views.request_approve, name='request_approve'),
    path('requests/<int:pk>/reject/', views.request_reject, name='request_reject'),

    # Maintenance Templates
    path('templates/', views.template_list, name='template_list'),
    path('templates/new/', views.template_create, name='template_create'),
    path('templates/<int:pk>/edit/', views.template_edit, name='template_edit'),
    path('templates/<int:pk>/apply/', views.template_apply, name='template_apply'),

    # Schedule management
    path('schedules/<int:pk>/toggle/', views.schedule_toggle, name='schedule_toggle'),
    path('schedules/<int:pk>/delete/', views.schedule_delete, name='schedule_delete'),

    # Technicians
    path('technicians/', views.technician_list, name='technician_list'),

    # Parts
    path('parts/', views.part_list, name='part_list'),
    path('parts/new/', views.part_create, name='part_create'),
    path('parts/<int:pk>/edit/', views.part_edit, name='part_edit'),

    # Reports
    path('reports/', views.reports, name='reports'),
    path('reports/export/work-orders/', views.report_export_workorders, name='report_export_workorders'),
    path('reports/export/pianos/', views.report_export_pianos, name='report_export_pianos'),

    # Public QR form
    path('maintenance_request/<uuid:token>/', views.maintenance_request_form,
         name='maintenance-request-form'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

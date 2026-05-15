from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from maintenance import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('signup/', views.signup, name='signup'),
    path('signup/pending/', views.signup_pending, name='signup_pending'),
    path('tech-mode/', views.toggle_tech_mode, name='toggle_tech_mode'),

    # Template views
    path('', views.dashboard, name='dashboard'),

    # Organizations
    path('organizations/', views.organization_list, name='organization_list'),
    path('organizations/new/', views.organization_create, name='organization_create'),
    path('organizations/<int:pk>/', views.organization_detail, name='organization_detail'),
    path('organizations/<int:pk>/edit/', views.organization_edit, name='organization_edit'),
    path('organizations/<int:pk>/delete/', views.organization_delete, name='organization_delete'),

    # Venues
    path('venues/', views.venue_list, name='venue_list'),
    path('venues/new/', views.venue_create, name='venue_create'),
    path('venues/<int:pk>/', views.venue_detail, name='venue_detail'),
    path('venues/<int:pk>/edit/', views.venue_edit, name='venue_edit'),
    path('venues/<int:pk>/delete/', views.venue_delete, name='venue_delete'),

    # Pianos
    path('pianos/', views.piano_list, name='piano_list'),
    path('pianos/new/', views.piano_create, name='piano_create'),
    path('pianos/bulk-edit/', views.piano_bulk_edit, name='piano_bulk_edit'),
    path('pianos/import/', views.piano_import_csv, name='piano_import'),
    path('pianos/import/sample/', views.piano_import_sample_csv, name='piano_import_sample'),
    path('pianos/qr-codes/', views.qr_codes, name='qr_codes'),
    path('pianos/qr-codes/csv/', views.qr_codes_csv, name='qr_codes_csv'),
    path('pianos/<int:pk>/', views.piano_detail, name='piano_detail'),
    path('pianos/<int:pk>/edit/', views.piano_edit, name='piano_edit'),
    path('pianos/<int:pk>/deactivate/', views.piano_deactivate, name='piano_deactivate'),
    path('pianos/<int:pk>/tags/add/', views.piano_add_tag, name='piano_add_tag'),
    path('pianos/<int:pk>/tags/<int:tag_pk>/remove/', views.piano_remove_tag, name='piano_remove_tag'),
    path('pianos/<int:pk>/tab/<str:tab>/', views.piano_tab, name='piano_tab'),
    path('pianos/<int:piano_pk>/condition/new/', views.condition_reading_create, name='condition_reading_create'),
    path('pianos/<int:pk>/photos/upload/', views.piano_photo_upload, name='piano_photo_upload'),
    path('pianos/<int:pk>/photos/<int:photo_pk>/set-profile/', views.piano_set_profile_photo, name='piano_set_profile_photo'),
    path('pianos/<int:pk>/photos/<int:photo_pk>/delete/', views.piano_photo_delete, name='piano_photo_delete'),

    # Work Orders
    path('work-orders/', views.workorder_list, name='workorder_list'),
    path('work-orders/export/csv/', views.workorder_export_csv, name='workorder_export_csv'),
    path('work-orders/new/', views.workorder_create, name='workorder_create'),
    path('work-orders/<int:pk>/', views.workorder_detail, name='workorder_detail'),
    path('work-orders/<int:pk>/edit/', views.workorder_edit, name='workorder_edit'),
    path('work-orders/<int:pk>/assign/', views.workorder_assign, name='workorder_assign'),
    path('work-orders/<int:pk>/delete/', views.workorder_delete, name='workorder_delete'),
    path('work-orders/<int:pk>/reopen/', views.workorder_reopen, name='workorder_reopen'),
    path('work-orders/<int:pk>/complete/', views.workorder_complete, name='workorder_complete'),
    path('work-orders/<int:pk>/log-work/', views.workorder_log_work, name='workorder_log_work'),

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
    path('technicians/new/', views.technician_create, name='technician_create'),
    path('technicians/<int:pk>/edit/', views.technician_edit, name='technician_edit'),
    path('technicians/report/', views.technician_report, name='technician_report'),
    path('technicians/report/csv/', views.technician_report_csv, name='technician_report_csv'),

    # Parts
    path('parts/', views.part_list, name='part_list'),
    path('parts/new/', views.part_create, name='part_create'),
    path('parts/<int:pk>/edit/', views.part_edit, name='part_edit'),

    # Settings
    path('settings/', views.settings_page, name='settings'),

    # Reports
    path('reports/', views.reports, name='reports'),
    path('reports/export/work-orders/', views.report_export_workorders, name='report_export_workorders'),
    path('reports/export/pianos/', views.report_export_pianos, name='report_export_pianos'),

    # Public QR form
    path('maintenance_request/<uuid:token>/', views.maintenance_request_form,
         name='maintenance-request-form'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

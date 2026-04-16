"""
Root URL configuration for piano_maintenance project.

Public routes:
  /report/<uuid>/   — MaintenanceRequest submission (no login required)

Protected routes (login required — enforced per-view with @login_required):
  /                 — Dashboard
  /pianos/          — Piano list
  /work-orders/     — WorkOrder list
  /admin/           — Django admin

Auth routes (built-in):
  /login/
  /logout/
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from maintenance import views

urlpatterns = [
    # ------------------------------------------------------------------
    # Django admin
    # ------------------------------------------------------------------
    path("admin/", admin.site.urls),

    # ------------------------------------------------------------------
    # Authentication (Django built-ins)
    # ------------------------------------------------------------------
    path("login/", auth_views.LoginView.as_view(template_name="maintenance/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # ------------------------------------------------------------------
    # Public — QR-code maintenance request (no login required)
    # ------------------------------------------------------------------
    path("report/<uuid:token>/", views.maintenance_request_view, name="maintenance_request"),

    # ------------------------------------------------------------------
    # Protected — require login (see @login_required in views.py)
    # ------------------------------------------------------------------
    path("", views.dashboard, name="dashboard"),
    path("pianos/", views.piano_list, name="piano_list"),
    path("pianos/<int:pk>/", views.piano_detail, name="piano_detail"),
    path("work-orders/", views.work_order_list, name="work_order_list"),
    path("work-orders/<int:pk>/", views.work_order_detail, name="work_order_detail"),
]

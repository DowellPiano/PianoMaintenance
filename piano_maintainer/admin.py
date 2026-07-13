from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig


class PlatformAdminSite(AdminSite):
    """Reserve Django's conventional admin for trusted platform operators."""

    def has_permission(self, request):
        return bool(
            request.user.is_active
            and request.user.is_superuser
        )


class PlatformAdminConfig(AdminConfig):
    default_site = "piano_maintainer.admin.PlatformAdminSite"

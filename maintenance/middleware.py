from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


class DemoAutoLoginMiddleware:
    """
    Auto-login a configured demo user when demo mode is enabled.

    This is intended for disposable demo deployments only. It leaves admin,
    static/media assets, and public QR maintenance request pages alone.
    """

    SKIPPED_PREFIXES = (
        "/admin/",
        "/maintenance_request/",
        settings.STATIC_URL,
        settings.MEDIA_URL,
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_auto_login(request):
            user = (
                get_user_model()
                .objects.filter(
                    username=settings.DEMO_AUTO_LOGIN_USERNAME,
                    is_active=True,
                )
                .first()
            )
            if user:
                login(
                    request,
                    user,
                    backend="django.contrib.auth.backends.ModelBackend",
                )
                if request.path == settings.LOGIN_URL:
                    return redirect(self._safe_redirect_url(request))

        return self.get_response(request)

    def _should_auto_login(self, request):
        if not settings.DEMO_AUTO_LOGIN:
            return False
        if request.user.is_authenticated:
            return False
        return not any(
            request.path.startswith(prefix)
            for prefix in self.SKIPPED_PREFIXES
            if prefix
        )

    def _safe_redirect_url(self, request):
        next_url = request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return next_url
        return settings.LOGIN_REDIRECT_URL

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def check_private_media_storage(app_configs, **kwargs):
    if settings.SUPABASE_S3_ENABLED:
        return []

    missing_keys = ", ".join(settings.SUPABASE_S3_MISSING_KEYS)
    detail = f" Missing settings: {missing_keys}." if missing_keys else ""
    return [
        Warning(
            "Private media will use local filesystem storage in production."
            + detail,
            hint=(
                "Configure every SUPABASE_S3_* setting and set "
                "SUPABASE_S3_REQUIRED=True."
            ),
            id="overtone.W001",
        )
    ]

from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Shared infrastructure (abstract base models, pagination, exception handling)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    label = "common"
    verbose_name = "Common"

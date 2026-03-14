from django.apps import AppConfig


class CmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cms"
    verbose_name = "CMS"

    def ready(self):
        """Import signals when Django apps are ready."""
        try:
            from . import signals  # noqa: F401
        except ImportError:
            pass

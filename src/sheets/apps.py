from django.apps import AppConfig


class SheetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sheets"

    def ready(self):
        """Import admin and signals when Django apps are ready."""
        try:
            from . import admin  # noqa
            from . import signals  # noqa
        except ImportError:
            pass

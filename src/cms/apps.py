from django.apps import AppConfig


class CmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cms"

    # noinspection PyMethodMayBeStatic
    def ready(self):
        """Import admin and signals when Django apps are ready."""
        try:
            from . import admin  # noqa
            from . import signals  # noqa
        except ImportError:
            pass

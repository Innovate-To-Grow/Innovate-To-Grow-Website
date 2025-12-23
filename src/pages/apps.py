from django.apps import AppConfig


class PagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pages"
    
    def ready(self):
        """Import admin when Django apps are ready."""
        try:
            from . import admin  # noqa
        except ImportError:
            pass
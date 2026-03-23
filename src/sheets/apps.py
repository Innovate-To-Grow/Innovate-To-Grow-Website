import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class SheetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sheets"

    def ready(self):
        """Import admin and signals when Django apps are ready."""
        try:
            from . import admin  # noqa
            from . import signals  # noqa
        except ImportError:
            # admin or signals modules are optional; ignore if not present
            logger.warning("sheets: could not import admin or signals modules")

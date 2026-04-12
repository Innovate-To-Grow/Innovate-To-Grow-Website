from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Core application for shared utilities and base models."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from django.contrib import admin

        from .admin.system_intelligence import get_system_intelligence_urls

        original_get_urls = admin.AdminSite.get_urls

        def patched_get_urls(site_self):
            return get_system_intelligence_urls() + original_get_urls(site_self)

        admin.AdminSite.get_urls = patched_get_urls

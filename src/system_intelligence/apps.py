from django.apps import AppConfig


class SystemIntelligenceConfig(AppConfig):
    """Admin AI assistant and ADK integration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "system_intelligence"

    def ready(self):
        from django.contrib import admin

        from .admin import get_system_intelligence_urls

        if getattr(admin.AdminSite, "_system_intelligence_urls_patched", False):
            return

        original_get_urls = admin.AdminSite.get_urls

        def patched_get_urls(site_self):
            return get_system_intelligence_urls() + original_get_urls(site_self)

        admin.AdminSite.get_urls = patched_get_urls
        admin.AdminSite._system_intelligence_urls_patched = True

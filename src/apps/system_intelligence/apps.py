from django.apps import AppConfig


class SystemIntelligenceConfig(AppConfig):
    """Admin AI assistant and agent integration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.system_intelligence"
    label = "system_intelligence"

    def ready(self):
        from django.contrib import admin

        from apps.core.services.background_jobs import register_job_kind

        from .admin import get_system_intelligence_urls
        from .services.tools.exports.cleanup import CLEANUP_JOB

        register_job_kind(
            CLEANUP_JOB, handler="apps.system_intelligence.services.tools.exports.cleanup.delete_export_job"
        )

        if getattr(admin.AdminSite, "_system_intelligence_urls_patched", False):
            return

        original_get_urls = admin.AdminSite.get_urls

        def patched_get_urls(site_self):
            return get_system_intelligence_urls() + original_get_urls(site_self)

        admin.AdminSite.get_urls = patched_get_urls
        admin.AdminSite._system_intelligence_urls_patched = True

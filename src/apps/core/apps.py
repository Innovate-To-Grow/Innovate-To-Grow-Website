from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Core application for shared utilities and base models."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self):
        from django.contrib import admin

        from .admin.infrastructure_status import get_infrastructure_status_urls

        if getattr(admin.AdminSite, "_core_infrastructure_status_urls_patched", False):
            return

        original_get_urls = admin.AdminSite.get_urls

        def patched_get_urls(site_self):
            return get_infrastructure_status_urls(site_self) + original_get_urls(site_self)

        admin.AdminSite.get_urls = patched_get_urls
        admin.AdminSite._core_infrastructure_status_urls_patched = True

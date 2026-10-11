from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Core application for shared utilities and base models."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self):
        from django.contrib import admin

        from .admin.legacy_view import get_legacy_view_admin_urls

        if getattr(admin.AdminSite, "_core_legacy_view_urls_patched", False):
            return

        original_get_urls = admin.AdminSite.get_urls

        def patched_get_urls(site_self):
            return get_legacy_view_admin_urls(site_self) + original_get_urls(site_self)

        admin.AdminSite.get_urls = patched_get_urls
        admin.AdminSite._core_legacy_view_urls_patched = True

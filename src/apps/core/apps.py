from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Core application for shared utilities and base models."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self):
        from django.contrib import admin

        from . import checks  # noqa: F401  # registers the system checks
        from .admin.legacy_view import get_legacy_view_admin_urls
        from .services.delivery_rates import Family, register_family
        from .services.delivery_rates import receivers as delivery_rate_receivers

        delivery_rate_receivers.connect()
        # The worker's claim-time gates and the inline batch sizes find the active email channel through this.
        register_family(Family.EMAIL, "apps.core.services.email.registry.active_rate_target")

        if getattr(admin.AdminSite, "_core_legacy_view_urls_patched", False):
            return

        original_get_urls = admin.AdminSite.get_urls

        def patched_get_urls(site_self):
            return get_legacy_view_admin_urls(site_self) + original_get_urls(site_self)

        admin.AdminSite.get_urls = patched_get_urls
        admin.AdminSite._core_legacy_view_urls_patched = True

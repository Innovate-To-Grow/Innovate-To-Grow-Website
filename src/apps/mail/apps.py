from django.apps import AppConfig


class MailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mail"
    label = "mail"
    verbose_name = "Mail"

    def ready(self):
        from django.contrib import admin

        from .admin.delivery_dashboard import get_delivery_dashboard_urls
        from .admin.inbox import get_inbox_urls
        from .admin.settings import get_mail_settings_urls

        # Guard against re-patching if ready() runs more than once (e.g. tests
        # using override_settings(INSTALLED_APPS=...) / modify_settings), which
        # would otherwise nest wrappers and duplicate the admin URLs.
        if not getattr(admin.AdminSite, "_mail_urls_patched", False):
            original_get_urls = admin.AdminSite.get_urls

            def patched_get_urls(site_self):
                return (
                    get_delivery_dashboard_urls()
                    + get_inbox_urls()
                    + get_mail_settings_urls()
                    + original_get_urls(site_self)
                )

            admin.AdminSite.get_urls = patched_get_urls
            admin.AdminSite._mail_urls_patched = True

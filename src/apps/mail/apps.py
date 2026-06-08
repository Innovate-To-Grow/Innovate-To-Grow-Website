from django.apps import AppConfig


class MailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mail"
    label = "mail"
    verbose_name = "Mail"

    def ready(self):
        from django.contrib import admin
        from django.db.models.signals import post_migrate

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

        # Reset orphaned "sending" campaigns after migration. A prior Gunicorn
        # worker could have been SIGTERMed mid-send, leaving a row in an
        # inconsistent state that blocks the resume button in the admin.
        post_migrate.connect(_reset_stuck_sending_campaigns, sender=self)


def _reset_stuck_sending_campaigns(sender, **kwargs):
    try:
        from django.db import connections

        from .models import EmailCampaign, SmsCampaign
    except Exception:
        return

    connection = connections[kwargs.get("using") or "default"]
    table_names = set(connection.introspection.table_names())
    error_message = "Campaign worker restarted mid-send; marked failed by recovery."
    if EmailCampaign._meta.db_table in table_names:
        EmailCampaign.objects.using(connection.alias).filter(status="sending").update(
            status="failed",
            error_message=error_message,
        )
    if SmsCampaign._meta.db_table in table_names:
        SmsCampaign.objects.using(connection.alias).filter(status="sending").update(
            status="failed",
            error_message=error_message,
        )

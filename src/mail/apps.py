from django.apps import AppConfig


class MailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mail"
    verbose_name = "Mail"

    def ready(self):
        from django.contrib import admin
        from django.db.models.signals import post_migrate

        from .admin.inbox import get_inbox_urls

        original_get_urls = admin.AdminSite.get_urls

        def patched_get_urls(site_self):
            return get_inbox_urls() + original_get_urls(site_self)

        admin.AdminSite.get_urls = patched_get_urls

        # Reset orphaned "sending" campaigns after migration. A prior Gunicorn
        # worker could have been SIGTERMed mid-send, leaving a row in an
        # inconsistent state that blocks the resume button in the admin.
        post_migrate.connect(_reset_stuck_sending_campaigns, sender=self)


def _reset_stuck_sending_campaigns(sender, **kwargs):
    try:
        from .models import EmailCampaign
    except Exception:
        return
    EmailCampaign.objects.filter(status="sending").update(
        status="failed",
        error_message="Campaign worker restarted mid-send; marked failed by recovery.",
    )

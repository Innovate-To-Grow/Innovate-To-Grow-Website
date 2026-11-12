from django.apps import AppConfig


class HelpdeskConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.helpdesk"
    label = "helpdesk"
    verbose_name = "Helpdesk"

    def ready(self):
        from .services.ingest.jobs import register_ingest
        from .services.intake.jobs import register_intake

        # The intake scans the Inbox on its own schedule and fills core's inbound queue; the ingest drains it into
        # tickets. The intake also describes itself to core, for the Email Monitoring card.
        register_intake()
        register_ingest()

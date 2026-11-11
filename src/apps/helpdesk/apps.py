from django.apps import AppConfig


class HelpdeskConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.helpdesk"
    label = "helpdesk"
    verbose_name = "Helpdesk"

    def ready(self):
        from .services.ingest.jobs import register_ingest

        # The ingest job drains core's inbound queue; core queues it by name after a scan records new mail.
        register_ingest()

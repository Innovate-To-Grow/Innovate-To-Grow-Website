from django.apps import AppConfig


class EventConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.event"
    label = "event"
    verbose_name = "Event"

    def ready(self):
        from . import signals  # noqa: F401

        register_background_jobs()


def register_background_jobs():
    from apps.core.services.background_jobs import register_job_kind

    register_job_kind(
        "event.registration_sheet_sync",
        handler="apps.event.services.registration_sheet_sync.jobs.sync_registration_sheet_job",
        state_handler="apps.event.services.registration_sheet_sync.jobs.sync_registration_sheet_job_state",
    )
    register_job_kind("event.ticket_email", handler="apps.event.services.ticket.jobs.send_ticket_email_job")

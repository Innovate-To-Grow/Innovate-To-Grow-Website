from django.apps import AppConfig


class AuthnConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authn"
    label = "authn"

    # noinspection PyMethodMayBeStatic
    def ready(self):
        try:
            from . import signals  # noqa: F401
        except ImportError:
            pass
        register_background_jobs()


def register_background_jobs():
    from apps.core.services.background_jobs import register_job_kind

    register_job_kind(
        "authn.member_sheet_sync",
        handler="apps.authn.services.members.sheet_sync.jobs.sync_member_sheet_job",
    )
    register_job_kind(
        "authn.notification_email",
        handler="apps.authn.services.email.notification_jobs.send_notification_email_job",
    )

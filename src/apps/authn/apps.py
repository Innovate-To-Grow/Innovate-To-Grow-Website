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
        register_request_limits()


def register_background_jobs():
    from apps.core.services.background_jobs import register_job_kind
    from apps.core.services.delivery_rates import Family, Lane

    register_job_kind(
        "authn.member_sheet_sync",
        handler="apps.authn.services.members.sheet_sync.jobs.sync_member_sheet_job",
    )
    # Security notices: transactional mail, claimed before campaign jobs.
    register_job_kind(
        "authn.notification_email",
        handler="apps.authn.services.email.notification_jobs.send_notification_email_job",
        family=Family.EMAIL,
        lane=Lane.TRANSACTIONAL,
    )


def register_request_limits():
    from apps.core.services.request_limits import register_priority_check

    # An anonymous code request is P0 only when it carries a valid anti-abuse proof (a signed-in member is P0
    # anyway); others are counted as unproven traffic, never promoted.
    register_priority_check("auth-code-send", "apps.authn.services.send_verification.priority.carries_valid_proof")

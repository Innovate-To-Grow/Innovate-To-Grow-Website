from django.apps import AppConfig


class CmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cms"
    label = "cms"

    # noinspection PyMethodMayBeStatic
    def ready(self):
        """Import admin and signals when Django apps are ready."""
        try:
            from . import admin  # noqa
            from . import signals  # noqa
        except ImportError:
            pass
        register_background_jobs()


def register_background_jobs():
    from apps.core.services.background_jobs import register_job_kind

    register_job_kind(
        "cms.amplify_redirects",
        handler="apps.cms.services.amplify.jobs.sync_amplify_redirects_job",
        state_handler="apps.cms.services.amplify.jobs.sync_amplify_redirect_job_state",
    )

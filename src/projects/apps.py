from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "projects"
    verbose_name = "Projects"

    # noinspection PyMethodMayBeStatic
    def ready(self):
        from . import signals  # noqa: F401

from django.apps import AppConfig


class NewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "news"
    verbose_name = "News"

    # noinspection PyMethodMayBeStatic
    def ready(self):
        from . import signals  # noqa: F401

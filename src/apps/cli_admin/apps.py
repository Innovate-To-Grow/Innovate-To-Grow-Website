from django.apps import AppConfig


class CliAdminConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cli_admin"
    label = "cli_admin"
    verbose_name = "CLI Admin"

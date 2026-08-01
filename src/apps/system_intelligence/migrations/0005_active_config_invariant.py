from django.db import migrations, models


def normalize_active_config(apps, schema_editor):
    Config = apps.get_model("system_intelligence", "SystemIntelligenceConfig")
    # The legacy loader selected the first active row by PK, falling back to
    # the most recently updated row when no row was active.
    active = Config.objects.filter(is_active=True).order_by("pk")
    keep = active.first()
    if keep is None:
        keep = Config.objects.order_by("-updated_at", "-pk").first()
        if keep is not None:
            Config.objects.filter(pk=keep.pk).update(is_active=True)
    else:
        active.exclude(pk=keep.pk).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("system_intelligence", "0004_systemintelligenceconfig_public_assistant_log_enabled_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_active_config, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="systemintelligenceconfig",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("is_active",),
                name="system_one_active_config",
            ),
        ),
    ]

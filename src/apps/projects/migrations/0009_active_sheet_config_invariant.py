from django.db import migrations, models


def normalize_active_config(apps, schema_editor):
    Config = apps.get_model("projects", "PastProjectsSheetConfig")
    # The pre-migration loader used ``filter(...).first()`` with no model
    # ordering, so Django selected the lowest primary key. Preserve that exact
    # runtime winner once before adding the uniqueness constraint.
    active = Config.objects.filter(is_active=True).order_by("pk")
    keep = active.first()
    if keep is not None:
        active.exclude(pk=keep.pk).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0008_pastprojectshare_version"),
    ]

    operations = [
        migrations.RunPython(normalize_active_config, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="pastprojectssheetconfig",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("is_active",),
                name="projects_one_active_sheet",
            ),
        ),
    ]

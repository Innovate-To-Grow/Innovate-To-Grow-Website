from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0007_project_resource_admin_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="pastprojectshare",
            name="version",
            field=models.PositiveBigIntegerField(
                default=1,
                db_default=1,
                editable=False,
                help_text="Monotonic snapshot version used to reject stale whole-document updates.",
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0006_pastprojectsynclog_update_delete_counts"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="pastprojectshare",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Project Resource Share",
                "verbose_name_plural": "Project Resource Shares",
            },
        ),
        migrations.AlterModelOptions(
            name="pastprojectssheetconfig",
            options={
                "verbose_name": "Project Resource",
                "verbose_name_plural": "Project Resources",
            },
        ),
        migrations.AlterModelOptions(
            name="pastprojectsynclog",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Project Resource Sync Log",
                "verbose_name_plural": "Project Resource Sync Logs",
            },
        ),
        migrations.AlterField(
            model_name="pastprojectssheetconfig",
            name="sheet_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="The spreadsheet ID containing project resource rows (the part of the URL after /d/).",
                max_length=255,
                verbose_name="Google Sheet ID",
            ),
        ),
    ]

from django.db import migrations, models

from apps.system_intelligence.models import export


class Migration(migrations.Migration):
    dependencies = [("system_intelligence", "0008_public_assistant_actor_budgets")]

    operations = [
        migrations.AddField(
            model_name="chatconversation",
            name="required_tool_apps",
            field=models.JSONField(editable=False, null=True),
        ),
        migrations.AlterField(
            model_name="chatconversation",
            name="required_tool_apps",
            field=models.JSONField(default=list, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name="systemintelligenceexport",
            name="file",
            field=models.FileField(blank=True, upload_to=export._export_upload_to),
        ),
        migrations.AddField(
            model_name="systemintelligenceexport",
            name="private_file",
            field=models.FileField(
                blank=True, max_length=255, storage=export.private_export_storage, upload_to=export._export_upload_to
            ),
        ),
    ]

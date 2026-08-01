from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_intelligence", "0005_active_config_invariant"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemintelligenceconfig",
            name="public_assistant_max_context_chars",
            field=models.PositiveIntegerField(
                default=24000,
                db_default=24000,
                help_text="Maximum public grounding-context characters included in a model request.",
                verbose_name="Public Max Context Characters",
            ),
        ),
        migrations.AddField(
            model_name="systemintelligenceconfig",
            name="public_assistant_max_estimated_input_tokens",
            field=models.PositiveIntegerField(
                default=12000,
                db_default=12000,
                help_text="Reject model requests whose estimated total input exceeds this limit.",
                verbose_name="Public Max Estimated Input Tokens",
            ),
        ),
        migrations.AddField(
            model_name="systemintelligenceconfig",
            name="public_assistant_max_history_chars",
            field=models.PositiveIntegerField(
                default=8000,
                db_default=8000,
                help_text=(
                    "Maximum combined characters retained from prior turns. "
                    "Oldest turns are trimmed first."
                ),
                verbose_name="Public Max Total History Characters",
            ),
        ),
    ]

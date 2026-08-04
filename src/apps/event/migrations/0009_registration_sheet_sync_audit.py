from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0008_event_date_range_and_registration_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="registrationsheetsynclog",
            name="cursor_from",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="registrationsheetsynclog",
            name="cursor_to",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="registrationsheetsynclog",
            name="selected_registration_ids",
            field=models.JSONField(blank=True, db_default=[], default=list),
        ),
    ]

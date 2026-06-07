from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0004_checkin_event_wide_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventregistration",
            name="ticket_login_token_hash",
            field=models.CharField(blank=True, default="", editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name="eventregistration",
            name="ticket_login_token_sent_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="eventregistration",
            name="ticket_login_token_used_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]

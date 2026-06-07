import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0005_ticket_login_token_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="ticket_login_validity_days",
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text="How long the login link in each ticket confirmation email stays valid (1-90 days).",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(90),
                ],
                verbose_name="Ticket login link validity (days)",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="ticket_login_reusable",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Allow attendees to sign in with their ticket email link repeatedly until it expires. "
                    "Off: each link works exactly once. Checked at login time, so unticking it later "
                    "immediately blocks further reuse of links already used for this event."
                ),
                verbose_name="Reusable ticket login links",
            ),
        ),
        # Ticket emails now issue unified mail.LoginLinkToken rows; the per-registration
        # signed-token state from 0005 is superseded.
        migrations.RemoveField(model_name="eventregistration", name="ticket_login_token_hash"),
        migrations.RemoveField(model_name="eventregistration", name="ticket_login_token_sent_at"),
        migrations.RemoveField(model_name="eventregistration", name="ticket_login_token_used_at"),
    ]

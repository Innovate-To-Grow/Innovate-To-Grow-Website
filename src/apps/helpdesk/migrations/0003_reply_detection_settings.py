"""Helpdesk settings for telling a person's reply from bulk mail: Exchange's bulk complaint level from which a message
counts as list or bulk mail (7), and how long after an email the site sent without a Message-ID a reply to it is
recognised by its sender and subject (30 days). Database defaults, so the previous release can keep saving the
settings while a deploy rolls out.
"""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("helpdesk", "0002_intake_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="helpdesksettings",
            name="bulk_bcl_threshold",
            field=models.PositiveSmallIntegerField(
                db_default=7,
                default=7,
                help_text="Exchange's bulk complaint level (BCL) from which a message counts as list or bulk mail (Exchange Online's own default bulk threshold is 7). A reply to an email the site sent is never bulk on this alone.",
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(9)],
            ),
        ),
        migrations.AddField(
            model_name="helpdesksettings",
            name="reply_match_window_days",
            field=models.PositiveSmallIntegerField(
                db_default=30,
                default=30,
                help_text="A reply to an email the site sent without a Message-ID it knows (one carrying a sign-in link) is recognised by its sender and subject when that email went out at most this many days before.",
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(180)],
            ),
        ),
    ]

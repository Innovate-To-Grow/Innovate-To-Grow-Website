"""Bound retention of unverified contact hints from left-organisation notices.

Existing hints predate source tracking and therefore cannot be retained safely; clear them during the upgrade. New
hints point to their inbound source and carry an explicit expiry. Aggregate notice counts and timestamps are not
changed.
"""

import django.db.models.deletion
from django.db import migrations, models


def clear_untracked_hints(apps, schema_editor):
    BouncedAddress = apps.get_model("mail", "BouncedAddress")
    BouncedAddress.objects.using(schema_editor.connection.alias).update(
        left_org_contact="",
        left_org_contact_kind="",
        left_org_contact_name="",
        left_org_contact_phone="",
        left_org_ticket=None,
    )


class Migration(migrations.Migration):
    dependencies = [("mail", "0029_alter_bouncedaddress_suggestion")]

    operations = [
        migrations.AlterField(
            model_name="bouncedaddress",
            name="left_org_contact",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                help_text=(
                    "The address the latest notice names instead (unverified and retained only for the review period)."
                ),
                max_length=254,
            ),
        ),
        migrations.AlterField(
            model_name="bouncedaddress",
            name="left_org_contact_phone",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                help_text=(
                    "Unverified US phone in the latest notice, retained only for the bounded hint-review period."
                ),
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="bouncedaddress",
            name="left_org_hint_expires_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="When the unverified contact hints must be cleared.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="bouncedaddress",
            name="left_org_hint_source",
            field=models.ForeignKey(
                blank=True,
                help_text="Inbound message that supplied the retained unverified contact hints.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="core.inboundmessage",
            ),
        ),
        # Reverse must clear hints again before dropping their source/expiry columns; otherwise an older image would
        # retain newly copied third-party PII indefinitely with no way to enforce this migration's TTL.
        migrations.RunPython(clear_untracked_hints, clear_untracked_hints),
    ]

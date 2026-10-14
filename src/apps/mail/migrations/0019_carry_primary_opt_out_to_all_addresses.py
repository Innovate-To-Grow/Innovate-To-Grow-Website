"""Carry a newsletter opt-out on the primary address over to the member's other addresses.

Until now the "subscribers" audience gated the whole member on the PRIMARY ``ContactEmail.subscribe`` flag, and the
one-click unsubscribe link and the account page's primary toggle cleared only that row. The per-address flag is now
authoritative, so without this step every member who opted out that way would start receiving newsletters again at
the secondary and other addresses, which still hold the model default ``subscribe=True``.

For every member whose primary address is unsubscribed, turn off the member's other addresses too: exactly the
audience before the change (those members received nothing). Idempotent; the reverse is a no-op because the old
flags cannot be told apart from later choices.
"""

from django.db import migrations
from django.db.models import Exists, OuterRef


def carry_primary_opt_out(apps, schema_editor):
    ContactEmail = apps.get_model("authn", "ContactEmail")
    opted_out_primary = ContactEmail.objects.filter(
        member_id=OuterRef("member_id"),
        email_type="primary",
        subscribe=False,
    )
    ContactEmail.objects.filter(member__isnull=False, subscribe=True).filter(Exists(opted_out_primary)).update(
        subscribe=False
    )


class Migration(migrations.Migration):
    dependencies = [
        ("authn", "0016_backfill_primary_email"),
        ("mail", "0018_rename_ses_message_id"),
    ]

    operations = [
        migrations.RunPython(carry_primary_opt_out, migrations.RunPython.noop),
    ]

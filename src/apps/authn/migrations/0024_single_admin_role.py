"""One Admin role: every active staff member gets every permission (the former I2G Master's).

- An inactive account loses Admin (``is_staff``), so reactivating it later never brings back a full Admin unasked.
- ``is_superuser`` becomes a mirror of ``is_staff`` for every row (``Member.save()`` keeps it so from now on).
- Pending admin invitations are cancelled: each was approved as "staff with no apps" and would now create a full
  Admin; send a new one where it is still wanted.

The member ids changed are printed to the migration log (no names or addresses). The reverse is a no-op: who was an
I2G Master, and what each admin's app grants were, cannot be told apart afterwards.
"""

from django.db import migrations
from django.db.models import F
from django.utils import timezone


def _report(label, ids):
    if ids:
        print(f"\n  {label} ({len(ids)}): {', '.join(str(pk) for pk in ids)}")


def single_admin_role(apps, schema_editor):
    alias = schema_editor.connection.alias
    Member = apps.get_model("authn", "Member")
    AdminInvitation = apps.get_model("authn", "AdminInvitation")
    members = Member.objects.using(alias)

    inactive = members.filter(is_staff=True, is_active=False)
    inactive_ids = sorted(inactive.values_list("pk", flat=True))
    inactive.update(is_staff=False, is_superuser=False)
    _report("Inactive accounts that lost Admin", inactive_ids)

    drifted = members.exclude(is_superuser=F("is_staff"))
    promoted = sorted(drifted.filter(is_staff=True).values_list("pk", flat=True))
    demoted = sorted(drifted.filter(is_staff=False).values_list("pk", flat=True))
    drifted.update(is_superuser=F("is_staff"))
    _report("Staff accounts that became full Admins", promoted)
    _report("Non-staff accounts whose superuser flag was cleared", demoted)

    pending = AdminInvitation.objects.using(alias).filter(status="pending")
    cancelled = pending.update(status="cancelled", updated_at=timezone.now())
    if cancelled:
        print(f"\n  Pending admin invitations cancelled: {cancelled}")


class Migration(migrations.Migration):
    dependencies = [
        ("authn", "0023_member_import_batch"),
    ]

    operations = [
        migrations.RunPython(single_admin_role, migrations.RunPython.noop),
    ]

"""Retire ``Member.admin_apps`` (per-app admin grants; every Admin now has every app).

Expand/contract, as ``event.0008``: the code stops reading and writing the column now, and the column is dropped in
a later release, once no task of an earlier release can run. Until then old tasks still select and write it, and new
code inserts members without it, so the physical NOT NULL column gets a database default first. The database-only
change comes before the state-only removal so that an SQLite table rebuild keeps the physical column. The contract
migration must add the field back to the state before removing it (as ``event.0012`` does for ``is_live``).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("authn", "0024_single_admin_role"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.AlterField(
                    model_name="member",
                    name="admin_apps",
                    field=models.JSONField(blank=True, default=list, db_default=[]),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="member", name="admin_apps"),
            ],
            database_operations=[],
        ),
    ]

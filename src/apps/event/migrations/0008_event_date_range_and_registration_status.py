from django.db import migrations, models


def normalize_phone_options(apps, schema_editor):
    Event = apps.get_model("event", "Event")
    Event.objects.filter(collect_phone=False, verify_phone=True).update(verify_phone=False)


class Migration(migrations.Migration):
    dependencies = [
        ("event", "0007_event_registration_open"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="date",
            field=models.DateField(verbose_name="Start date"),
        ),
        migrations.AddField(
            model_name="event",
            name="end_date",
            field=models.DateField(null=True, verbose_name="End date"),
        ),
        migrations.RunPython(normalize_phone_options, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="event",
            name="collect_phone",
            field=models.BooleanField(
                default=False,
                help_text="Prompt registrants to enter a phone number on the registration form.",
                verbose_name="Prompt for Phone Number",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="verify_phone",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Require phone number verification via SMS code. "
                    "Only available when Prompt for Phone Number is enabled."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="event",
            constraint=models.CheckConstraint(
                condition=models.Q(("collect_phone", True), ("verify_phone", False), _connector="OR"),
                name="event_verify_phone_requires_prompt",
            ),
        ),
        # New application tasks no longer include ``is_live`` in INSERTs, so
        # the legacy physical NOT NULL column needs a persistent database
        # default while old and new tasks overlap. Keep this database-only
        # alteration before the state-only non-null ``end_date`` change so an
        # SQLite table rebuild preserves the physical nullable end date.
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.AlterField(
                    model_name="event",
                    name="is_live",
                    field=models.BooleanField(default=False, db_default=False),
                ),
            ],
        ),
        # Keep the physical column nullable and the range constraint unmaterialized
        # for one rolling-deploy window. Old ECS tasks do not know about
        # ``end_date`` and may still insert rows or change ``date`` while new
        # tasks are starting. These state-only operations intentionally come
        # after every schema operation so SQLite table rebuilds also preserve
        # the expand-phase schema. The new application state and forms enforce
        # both rules; a later contract migration can backfill and materialize
        # them after every old task has drained.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="event",
                    name="end_date",
                    field=models.DateField(verbose_name="End date"),
                ),
                migrations.AddConstraint(
                    model_name="event",
                    constraint=models.CheckConstraint(
                        condition=models.Q(("end_date__gte", models.F("date"))),
                        name="event_end_date_gte_start_date",
                    ),
                ),
            ],
            database_operations=[],
        ),
        # Remove ``is_live`` from Django immediately, but leave the physical
        # column in place for the same rolling-deploy compatibility window.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="event",
                    name="is_live",
                ),
            ],
            database_operations=[],
        ),
    ]

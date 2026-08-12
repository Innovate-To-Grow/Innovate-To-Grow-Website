import datetime

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class EventRangeAndStatusMigrationTest(TransactionTestCase):
    migrate_from = [("event", "0007_event_registration_open")]
    migrate_to = [("event", "0008_event_date_range_and_registration_status")]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_expand_phase_preserves_status_normalizes_phone_and_allows_old_tasks(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldEvent = old_apps.get_model("event", "Event")

        closed = OldEvent.objects.create(
            name="Closed featured Event",
            slug="closed-featured-event",
            date=datetime.date(2026, 5, 14),
            location="Room",
            description="Migration check.",
            is_live=True,
            registration_open=False,
            collect_phone=False,
            verify_phone=True,
        )
        opened = OldEvent.objects.create(
            name="Open Event",
            slug="open-event",
            date=datetime.date(2026, 6, 2),
            location="Room",
            description="Migration check.",
            is_live=False,
            registration_open=True,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        NewEvent = new_apps.get_model("event", "Event")

        migrated_closed = NewEvent.objects.get(pk=closed.pk)
        migrated_open = NewEvent.objects.get(pk=opened.pk)
        # Existing ranges stay null during the expand phase so an old task can
        # still move the only date in either direction without creating a
        # stale range or tripping a new physical constraint.
        self.assertIsNone(migrated_closed.end_date)
        self.assertIsNone(migrated_open.end_date)
        self.assertFalse(migrated_closed.registration_open)
        self.assertTrue(migrated_open.registration_open)
        self.assertFalse(migrated_closed.verify_phone)
        self.assertNotIn("is_live", {field.name for field in NewEvent._meta.get_fields()})
        self.assertFalse(NewEvent._meta.get_field("end_date").null)
        self.assertIn(
            "event_end_date_gte_start_date",
            {constraint.name for constraint in NewEvent._meta.constraints},
        )
        with connection.cursor() as cursor:
            physical_columns = {
                column.name: column for column in connection.introspection.get_table_description(cursor, "event_event")
            }
            physical_constraints = connection.introspection.get_constraints(cursor, "event_event")
        self.assertIn("is_live", physical_columns)
        self.assertTrue(physical_columns["end_date"].null_ok)
        self.assertNotIn("event_end_date_gte_start_date", physical_constraints)
        self.assertIn("event_verify_phone_requires_prompt", physical_constraints)

        OldEvent.objects.filter(pk=closed.pk).update(date=datetime.date(2026, 8, 14))
        OldEvent.objects.filter(pk=opened.pk).update(date=datetime.date(2026, 4, 2))
        migrated_closed.refresh_from_db()
        migrated_open.refresh_from_db()
        self.assertEqual(migrated_closed.date, datetime.date(2026, 8, 14))
        self.assertEqual(migrated_open.date, datetime.date(2026, 4, 2))
        self.assertIsNone(migrated_closed.end_date)
        self.assertIsNone(migrated_open.end_date)

        # A new task omits the removed physical column. Its database default
        # keeps the INSERT valid and gives still-running old tasks a safe value.
        created_by_new_task = NewEvent.objects.create(
            name="Created by new task",
            slug="created-by-new-task",
            date=datetime.date(2026, 7, 10),
            end_date=datetime.date(2026, 7, 10),
            location="Room",
            description="Rolling deployment check.",
        )
        self.assertFalse(OldEvent.objects.get(pk=created_by_new_task.pk).is_live)

        # A still-running old task omits the new column. It must remain able to
        # INSERT until the old deployment has drained; new code resolves null
        # end dates to the start date at read time.
        created_by_old_task = OldEvent.objects.create(
            name="Created by old task",
            slug="created-by-old-task",
            date=datetime.date(2026, 7, 11),
            location="Room",
            description="Rolling deployment check.",
            is_live=False,
            registration_open=True,
        )
        self.assertIsNone(NewEvent.objects.get(pk=created_by_old_task.pk).end_date)

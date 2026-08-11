import datetime

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RegistrationOpenSeedMigrationTest(TransactionTestCase):
    migrate_from = [("event", "0006_ticket_login_unification")]
    migrate_to = [("event", "0007_event_registration_open")]

    def tearDown(self):
        # Restore the schema to the latest migration state. The backward
        # migrate below also unapplies every migration that depends on a
        # later event migration, and migrating forward only to `migrate_to`
        # would leave those unapplied — poisoning the schema for
        # TransactionTestCases that run after this one in a single-process
        # full-suite run.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_live_events_seeded_open_and_others_stay_closed(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Event = old_apps.get_model("event", "Event")
        live = Event.objects.create(
            name="Live Event",
            slug="live-event",
            date=datetime.date(2026, 5, 3),
            location="Room",
            description="Migration check.",
            is_live=True,
        )
        dormant = Event.objects.create(
            name="Dormant Event",
            slug="dormant-event",
            date=datetime.date(2026, 6, 3),
            location="Room",
            description="Migration check.",
            is_live=False,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        NewEvent = new_apps.get_model("event", "Event")

        self.assertTrue(NewEvent.objects.get(pk=live.pk).registration_open)
        self.assertFalse(NewEvent.objects.get(pk=dormant.pk).registration_open)

import datetime

from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SheetSyncManagementMigrationTest(TransactionTestCase):
    migrate_from = [("event", "0012_unified_contact_settings")]
    migrate_to = [("event", "0013_registration_sheet_sync_management")]

    def setUp(self):
        cache.clear()

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_additive_models_preserve_expand_schema_and_legacy_log_writers(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldEvent = old_apps.get_model("event", "Event")
        OldLog = old_apps.get_model("event", "RegistrationSheetSyncLog")
        event = OldEvent.objects.create(
            name="Legacy linked event",
            slug="legacy-linked-event",
            date=datetime.date(2026, 9, 1),
            end_date=None,
            location="Migration room",
            description="Migration fixture.",
            registration_sheet_id="fixture-sheet",
        )
        existing = OldLog.objects.create(event=event, sync_type="append", status="success")
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        NewLog = new_apps.get_model("event", "RegistrationSheetSyncLog")
        SyncConfig = new_apps.get_model("event", "RegistrationSheetSyncConfig")
        self.assertEqual(NewLog.objects.get(pk=existing.pk).details, {})
        old_written = OldLog.objects.create(event=event, sync_type="append", status="success")
        self.assertEqual(NewLog.objects.get(pk=old_written.pk).details, {})
        config = SyncConfig.objects.create(event_id=event.pk)
        self.assertEqual(
            (config.sync_mode, config.debounce_seconds, config.max_delay_seconds, config.interval_minutes),
            ("automatic", 15, 60, 5),
        )
        self.assertEqual(config.header_row, 1)
        self.assertEqual(config.field_settings, {})
        self.assertEqual(config.requested_generation, 0)
        with connection.cursor() as cursor:
            columns = {
                column.name: column for column in connection.introspection.get_table_description(cursor, "event_event")
            }
            constraints = connection.introspection.get_constraints(cursor, "event_event")
        self.assertIn("is_live", columns)
        self.assertTrue(columns["end_date"].null_ok)
        self.assertNotIn("event_end_date_gte_start_date", constraints)

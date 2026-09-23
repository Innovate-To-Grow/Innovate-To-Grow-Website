import datetime

from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.event.tests.helpers import make_member


class ContactSettingsMigrationTest(TransactionTestCase):
    migrate_from = [("event", "0011_currentprojectschedule_auto_sync_help_text")]
    migrate_to = [("event", "0012_unified_contact_settings")]

    def setUp(self):
        cache.clear()

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    @staticmethod
    def event_data(name, **extra):
        return {
            "name": name,
            "slug": name.lower().replace(" ", "-"),
            "date": datetime.date(2026, 5, 14),
            "end_date": None,
            "location": "Migration test room",
            "description": "Isolated contact settings migration test.",
            **extra,
        }

    def test_backfill_preserves_legacy_phone_requirement_and_expand_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldEvent = old_apps.get_model("event", "Event")
        required = OldEvent.objects.create(**self.event_data("Verified phone", collect_phone=True, verify_phone=True))
        optional = OldEvent.objects.create(**self.event_data("Optional phone", collect_phone=True))
        hidden = OldEvent.objects.create(**self.event_data("Hidden contacts"))

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        NewEvent = new_apps.get_model("event", "Event")

        self.assertTrue(NewEvent.objects.get(pk=required.pk).require_phone)
        self.assertFalse(NewEvent.objects.get(pk=optional.pk).require_phone)
        self.assertFalse(NewEvent.objects.get(pk=hidden.pk).require_phone)
        for event in NewEvent.objects.all():
            self.assertFalse(event.verify_secondary_email)
            self.assertFalse(event.require_secondary_email)
            self.assertIsNone(event.end_date)
        self.assertNotIn("is_live", {field.name for field in NewEvent._meta.get_fields()})
        self.assertFalse(NewEvent._meta.get_field("end_date").null)
        self.assertIn("event_end_date_gte_start_date", {constraint.name for constraint in NewEvent._meta.constraints})

        with connection.cursor() as cursor:
            columns = {
                column.name: column for column in connection.introspection.get_table_description(cursor, "event_event")
            }
            constraints = connection.introspection.get_constraints(cursor, "event_event")
        self.assertIn("is_live", columns)
        self.assertTrue(columns["end_date"].null_ok)
        self.assertNotIn("event_end_date_gte_start_date", constraints)
        for name in (
            "event_verify_phone_requires_prompt",
            "event_require_phone_requires_collect",
            "event_verify_email_requires_collect",
            "event_require_email_requires_collect",
        ):
            self.assertIn(name, constraints)

        # A previous application version omits all new settings on INSERT.
        old_created = OldEvent.objects.create(**self.event_data("Old writer", collect_phone=True, verify_phone=True))
        new_loaded = NewEvent.objects.get(pk=old_created.pk)
        self.assertFalse(new_loaded.require_phone)
        self.assertFalse(new_loaded.verify_secondary_email)
        self.assertFalse(new_loaded.require_secondary_email)
        self.assertIsNone(new_loaded.end_date)
        OldEvent.objects.filter(pk=required.pk).update(date=datetime.date(2026, 9, 1))
        required_new = NewEvent.objects.get(pk=required.pk)
        self.assertEqual(required_new.date, datetime.date(2026, 9, 1))
        self.assertIsNone(required_new.end_date)

        # Legacy admins cannot represent the independent required flag. During
        # overlap they must use the new admin to disable collection for an event
        # backfilled as required; rejecting preserves the invariant and data.
        with self.assertRaises(IntegrityError), transaction.atomic():
            OldEvent.objects.filter(pk=required.pk).update(collect_phone=False, verify_phone=False)
        required_new.refresh_from_db()
        self.assertTrue(required_new.collect_phone)
        self.assertTrue(required_new.verify_phone)
        self.assertTrue(required_new.require_phone)
        NewEvent.objects.filter(pk=required.pk).update(collect_phone=False, verify_phone=False, require_phone=False)
        required_new.refresh_from_db()
        self.assertFalse(required_new.collect_phone)
        self.assertFalse(required_new.require_phone)

        # New writers omit the legacy column, which must retain its DB default.
        new_created = NewEvent.objects.create(**self.event_data("New writer", end_date=datetime.date(2026, 5, 14)))
        with connection.cursor() as cursor:
            cursor.execute("SELECT is_live FROM event_event WHERE slug = %s", [new_created.slug])
            self.assertFalse(cursor.fetchone()[0])

    def test_registration_verified_flag_defaults_false_for_old_rows_and_writers(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Event = old_apps.get_model("event", "Event")
        Ticket = old_apps.get_model("event", "Ticket")
        OldRegistration = old_apps.get_model("event", "EventRegistration")
        event = Event.objects.create(**self.event_data("Registration migration"))
        ticket = Ticket.objects.create(event=event, name="General")
        member = make_member()
        old_registration = OldRegistration.objects.create(
            event=event,
            ticket=ticket,
            member_id=member.pk,
            attendee_secondary_email="secondary@example.com",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        NewRegistration = new_apps.get_model("event", "EventRegistration")
        self.assertFalse(NewRegistration.objects.get(pk=old_registration.pk).secondary_email_verified)

        other_member = make_member(email="other-migration@example.com")
        old_created = OldRegistration.objects.create(event=event, ticket=ticket, member_id=other_member.pk)
        self.assertFalse(NewRegistration.objects.get(pk=old_created.pk).secondary_email_verified)

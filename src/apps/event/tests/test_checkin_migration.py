import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class CheckInEventWideMigrationTest(TransactionTestCase):
    migrate_from = [("event", "0003_add_schedule_sync_log")]
    migrate_to = [("event", "0004_checkin_event_wide_unique")]

    def test_duplicate_checkin_records_keep_earliest_record(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Event = old_apps.get_model("event", "Event")
        Ticket = old_apps.get_model("event", "Ticket")
        EventRegistration = old_apps.get_model("event", "EventRegistration")
        CheckIn = old_apps.get_model("event", "CheckIn")
        CheckInRecord = old_apps.get_model("event", "CheckInRecord")

        member = get_user_model().objects.create_user(
            password="",
            first_name="Migration",
            last_name="User",
            is_active=True,
        )
        event = Event.objects.create(
            name="Migration Event",
            slug="migration-event",
            date=datetime.date(2026, 5, 3),
            location="Room",
            description="Migration check.",
        )
        ticket = Ticket.objects.create(event=event, name="General", barcode="MIGRATION-BARCODE")
        registration = EventRegistration.objects.create(
            member_id=member.pk,
            event=event,
            ticket=ticket,
            ticket_code="I2G-MIGRATION",
        )
        first_station = CheckIn.objects.create(event=event, name="First")
        second_station = CheckIn.objects.create(event=event, name="Second")
        first = CheckInRecord.objects.create(check_in=first_station, registration=registration)
        second = CheckInRecord.objects.create(check_in=second_station, registration=registration)
        CheckInRecord.objects.filter(pk=first.pk).update(created_at=timezone.now() - datetime.timedelta(minutes=5))
        CheckInRecord.objects.filter(pk=second.pk).update(created_at=timezone.now())

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        NewCheckInRecord = new_apps.get_model("event", "CheckInRecord")

        records = list(NewCheckInRecord.objects.filter(registration_id=registration.pk))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].pk, first.pk)
        self.assertEqual(records[0].check_in_id, first_station.pk)

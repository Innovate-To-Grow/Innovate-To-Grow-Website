import datetime

from django.test import TestCase
from django.utils import timezone

from apps.event.models import (
    CheckIn,
    CheckInRecord,
    CurrentProject,
    CurrentProjectSchedule,
    EventAgendaItem,
    EventScheduleSection,
    EventScheduleSlot,
    EventScheduleTrack,
    RegistrationSheetSyncLog,
    ScheduleSyncLog,
)
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket


class CurrentProjectScheduleSyncDueTest(TestCase):
    def test_sync_not_due_when_auto_disabled(self):
        config = CurrentProjectSchedule(auto_sync_enabled=False)
        self.assertFalse(config.sync_is_due)

    def test_sync_due_when_never_synced(self):
        config = CurrentProjectSchedule(auto_sync_enabled=True, last_synced_at=None)
        self.assertTrue(config.sync_is_due)

    def test_sync_due_when_interval_elapsed(self):
        config = CurrentProjectSchedule(
            auto_sync_enabled=True,
            sync_interval_minutes=10,
            last_synced_at=timezone.now() - datetime.timedelta(minutes=30),
        )
        self.assertTrue(config.sync_is_due)

    def test_sync_not_due_within_interval(self):
        config = CurrentProjectSchedule(
            auto_sync_enabled=True,
            sync_interval_minutes=60,
            last_synced_at=timezone.now() - datetime.timedelta(minutes=5),
        )
        self.assertFalse(config.sync_is_due)


class CurrentProjectStrTest(TestCase):
    def setUp(self):
        self.config = CurrentProjectSchedule.objects.create(name="Demo Day")

    def test_str_with_team_number(self):
        project = CurrentProject.objects.create(
            schedule=self.config,
            team_number="CAP-101",
            project_title="Smart Farm",
        )
        self.assertEqual(str(project), "Team CAP-101 - Smart Farm")

    def test_str_without_team_number(self):
        project = CurrentProject.objects.create(
            schedule=self.config,
            team_number="",
            project_title="Standalone Project",
        )
        self.assertEqual(str(project), "Standalone Project")


class CheckInModelStrTest(TestCase):
    def setUp(self):
        self.event = make_event(name="Str Event")
        self.ticket = make_ticket(self.event, name="GA")
        self.member = make_member(email="str-member@example.com", first_name="Ada", last_name="Lovelace")
        self.registration = make_registration(self.member, self.event, self.ticket)

    def test_checkin_scan_count(self):
        check_in = CheckIn.objects.create(event=self.event, name="Main")
        self.assertEqual(check_in.scan_count, 0)
        CheckInRecord.objects.create(check_in=check_in, registration=self.registration)
        self.assertEqual(check_in.scan_count, 1)

    def test_checkin_record_str(self):
        check_in = CheckIn.objects.create(event=self.event, name="Main Gate")
        record = CheckInRecord.objects.create(check_in=check_in, registration=self.registration)
        self.assertEqual(str(record), f"{self.registration.attendee_name} @ Main Gate")


class SyncLogStrTest(TestCase):
    def setUp(self):
        self.event = make_event(name="Sync Log Event")
        self.config = CurrentProjectSchedule.objects.create(name="Demo Day")

    def test_registration_sheet_sync_log_str(self):
        log = RegistrationSheetSyncLog.objects.create(
            event=self.event,
            sync_type=RegistrationSheetSyncLog.SyncType.FULL,
            status=RegistrationSheetSyncLog.Status.SUCCESS,
        )
        self.assertEqual(str(log), "Sync Log Event — Full Sync — Success")

    def test_schedule_sync_log_str(self):
        log = ScheduleSyncLog.objects.create(
            config=self.config,
            sync_type=ScheduleSyncLog.SyncType.AUTO,
            status=ScheduleSyncLog.Status.FAILED,
        )
        self.assertEqual(str(log), "Demo Day — Auto Sync — Failed")


class ScheduleModelsStrTest(TestCase):
    def setUp(self):
        self.config = CurrentProjectSchedule.objects.create(name="Demo Day")
        self.section = EventScheduleSection.objects.create(config=self.config, code="CAP", label="CAP")
        self.track = EventScheduleTrack.objects.create(section=self.section, track_number=3)

    def test_section_str(self):
        self.assertEqual(str(self.section), "Demo Day - CAP")

    def test_track_str(self):
        self.assertEqual(str(self.track), "Demo Day - Track 3")

    def test_slot_str(self):
        slot = EventScheduleSlot.objects.create(track=self.track, slot_order=2)
        self.assertEqual(str(slot), "Demo Day - Track 3 - Slot 2")

    def test_agenda_item_str(self):
        item = EventAgendaItem.objects.create(
            config=self.config,
            section_type=EventAgendaItem.SectionType.EXPO,
            time_label="1:00",
            title="Expo Opens",
        )
        self.assertEqual(str(item), "Demo Day - Expo Opens")

from django.test import TestCase

from apps.event.models import (
    CurrentProjectSchedule,
    EventAgendaItem,
    EventScheduleSection,
    EventScheduleSlot,
    EventScheduleTrack,
    RegistrationSheetSyncLog,
    ScheduleSyncLog,
)
from apps.event.tests.helpers import make_event


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
        self.assertEqual(str(log), "Sync Log Event — Manual sync — Success")

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

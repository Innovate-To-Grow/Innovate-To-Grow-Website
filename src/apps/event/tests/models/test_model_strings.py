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

    def test_recent_failed_auto_attempt_counts_toward_the_interval(self):
        config = CurrentProjectSchedule.objects.create(
            name="Demo Day", auto_sync_enabled=True, sync_interval_minutes=60, last_synced_at=None
        )
        ScheduleSyncLog.objects.create(
            config=config, sync_type=ScheduleSyncLog.SyncType.AUTO, status=ScheduleSyncLog.Status.FAILED
        )
        self.assertFalse(config.sync_is_due)

    def test_old_failed_auto_attempt_does_not_block_the_next_run(self):
        config = CurrentProjectSchedule.objects.create(
            name="Demo Day", auto_sync_enabled=True, sync_interval_minutes=10, last_synced_at=None
        )
        log = ScheduleSyncLog.objects.create(
            config=config, sync_type=ScheduleSyncLog.SyncType.AUTO, status=ScheduleSyncLog.Status.FAILED
        )
        ScheduleSyncLog.objects.filter(pk=log.pk).update(created_at=timezone.now() - datetime.timedelta(minutes=30))
        self.assertTrue(config.sync_is_due)

    def test_failed_manual_pull_does_not_delay_auto_sync(self):
        config = CurrentProjectSchedule.objects.create(
            name="Demo Day", auto_sync_enabled=True, sync_interval_minutes=60, last_synced_at=None
        )
        ScheduleSyncLog.objects.create(
            config=config, sync_type=ScheduleSyncLog.SyncType.MANUAL, status=ScheduleSyncLog.Status.FAILED
        )
        self.assertTrue(config.sync_is_due)


class CurrentProjectScheduleLoadByIdTest(TestCase):
    def test_returns_any_row_by_id(self):
        CurrentProjectSchedule.objects.create(name="2026")
        archived = CurrentProjectSchedule.objects.create(name="2025", is_active=False)
        self.assertEqual(CurrentProjectSchedule.load_by_id(str(archived.pk)), archived)
        self.assertEqual(CurrentProjectSchedule.load_by_id(archived.pk), archived)

    def test_returns_none_for_unknown_blank_or_malformed_ids(self):
        for raw in ("", None, "not-a-uuid", 12, "00000000-0000-0000-0000-000000000000"):
            with self.subTest(raw=raw):
                self.assertIsNone(CurrentProjectSchedule.load_by_id(raw))


class CurrentProjectScheduleActivationTest(TestCase):
    def test_activating_a_schedule_stops_auto_sync_on_the_rows_it_archives(self):
        previous = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", auto_sync_enabled=True)
        current = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", auto_sync_enabled=True)

        previous.refresh_from_db()
        current.refresh_from_db()
        self.assertFalse(previous.is_active)
        self.assertFalse(previous.auto_sync_enabled)
        self.assertTrue(current.is_active)
        self.assertTrue(current.auto_sync_enabled)

    def test_saving_the_active_schedule_again_keeps_its_own_auto_sync(self):
        current = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", auto_sync_enabled=True)
        current.name = "Innovate to Grow 2026 (Spring)"
        current.save()
        current.refresh_from_db()
        self.assertTrue(current.auto_sync_enabled)

    def test_deactivating_the_active_schedule_stops_its_auto_sync(self):
        # The admin's two-step habit (deactivate the old row, then activate the
        # new one) must archive auto-sync just like a one-step activation does.
        current = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", auto_sync_enabled=True)
        current.is_active = False
        current.save()
        current.refresh_from_db()
        self.assertFalse(current.is_active)
        self.assertFalse(current.auto_sync_enabled)

    def test_deactivating_with_update_fields_still_persists_the_auto_sync_change(self):
        current = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", auto_sync_enabled=True)
        current.is_active = False
        current.save(update_fields=["is_active"])
        current.refresh_from_db()
        self.assertFalse(current.auto_sync_enabled)

    def test_editing_an_inactive_schedule_keeps_its_auto_sync_choice(self):
        previous = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        previous.auto_sync_enabled = True
        previous.name = "Innovate to Grow 2025 (archived)"
        previous.save()
        previous.refresh_from_db()
        self.assertTrue(previous.auto_sync_enabled)

    def test_one_step_activation_passes_model_validation(self):
        # full_clean() runs ModelForm-style constraint validation; the
        # single-active constraint must not reject activating a second row.
        CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025")
        incoming = CurrentProjectSchedule(name="Innovate to Grow 2026", is_active=True)
        incoming.full_clean()
        incoming.save()
        self.assertEqual(CurrentProjectSchedule.objects.filter(is_active=True).count(), 1)
        self.assertTrue(CurrentProjectSchedule.objects.get(name="Innovate to Grow 2026").is_active)

    def test_archived_schedule_can_opt_back_into_auto_sync(self):
        previous = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025")
        CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026")
        previous.refresh_from_db()
        previous.auto_sync_enabled = True
        previous.save()
        previous.refresh_from_db()
        self.assertFalse(previous.is_active)
        self.assertTrue(previous.auto_sync_enabled)


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

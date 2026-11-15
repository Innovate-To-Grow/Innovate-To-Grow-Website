from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.db import IntegrityError

from apps.core.models import EmailMonitorState
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings
from apps.helpdesk.tests.intake.test_intake_scan import IntakeTestCase, row

from ...models import IntakeState
from ...services.intake import state as intake_state
from ..corpus import SITE
from ..helpers import make_admin


class StateTests(IntakeTestCase):
    def test_the_lease_lets_one_scan_run_and_an_expired_one_is_taken_over(self):
        intake_state.state_for(SITE)

        self.assertIsNotNone(intake_state.acquire_lease(SITE, self.now))
        self.assertIsNone(intake_state.acquire_lease(SITE, self.now + timedelta(minutes=1)))
        later = self.now + timedelta(seconds=901)
        self.assertIsNotNone(intake_state.acquire_lease(SITE, later))

    def test_a_row_another_process_created_meanwhile_is_used(self):
        created = IntakeState.objects.create(mailbox=SITE)

        with patch.object(IntakeState.objects, "get_or_create", side_effect=IntegrityError("duplicate key")):
            self.assertEqual(intake_state.state_for(SITE).pk, created.pk)

    def test_a_scan_whose_lease_was_released_saves_nothing(self):
        intake_state.state_for(SITE)
        token = intake_state.acquire_lease(SITE, self.ago(hours=1))
        intake_state.rescan_since(SITE, self.ago(days=1), now=self.now)  # the lease expired: released

        intake_state.finish(SITE, token, checkpoint=self.now, stats={"listed": 1})

        self.assertEqual((row().checkpoint_at, row().last_run_stats), (self.ago(days=1), {}))

    def test_pause_and_resume_are_recorded_once_each(self):
        staff = make_admin(apps=["helpdesk"], email="agent@example.com")

        self.assertTrue(intake_state.set_paused(SITE, True, actor=staff))
        self.assertFalse(intake_state.set_paused(SITE, True, actor=staff))
        with self.assertLogs("apps.helpdesk.services.intake.state", level="INFO") as logs:
            self.assertTrue(intake_state.set_paused(SITE, False))

        self.assertEqual(list(LogEntry.objects.values_list("change_message", flat=True)), ["Intake paused."])
        self.assertIn("action=resume mailbox=i2g@ucmerced.edu actor=-", logs.records[0].getMessage())
        self.assertFalse(intake_state.is_paused(SITE))

    def test_the_lookback_is_bounded_audited_and_clamped_whatever_the_row_holds(self):
        staff = make_admin(apps=["helpdesk"], email="agent@example.com")
        with monitoring_settings(inbox_max_lookback_days=10, inbox_initial_lookback_hours=72):
            self.assertEqual(intake_state.lookback_bounds(), (1, 240))
            with self.assertRaises(ValueError):
                intake_state.set_lookback(SITE, 241)
            self.assertIsNone(intake_state.set_lookback(SITE, 200, actor=staff))
            self.assertEqual(intake_state.set_lookback(SITE, 200, actor=staff), 200)
            IntakeState.objects.filter(mailbox=SITE).update(initial_lookback_hours=5000)
            self.assertEqual(intake_state.lookback_hours(row()), 240)
            self.assertEqual(intake_state.lookback_hours(None), 72)
        with monitoring_settings(inbox_initial_lookback_hours=0):
            self.assertEqual(intake_state.default_lookback_hours(), 1)

        self.assertEqual(LogEntry.objects.get().change_message, "First-scan lookback: default (72 h) → 200 h.")

    def test_a_rescan_moves_the_checkpoint_back_only_when_that_is_safe(self):
        staff = make_admin(apps=["helpdesk"], email="agent@example.com")
        IntakeState.objects.create(mailbox=SITE, checkpoint_at=self.ago(minutes=10))
        with monitoring_settings(inbox_max_lookback_days=30):
            self.assertEqual(
                intake_state.rescan_since(SITE, self.now + timedelta(hours=1), now=self.now).status, "future"
            )
            self.assertEqual(intake_state.rescan_since(SITE, self.ago(days=31), now=self.now).status, "too_early")
            self.assertEqual(intake_state.rescan_since(SITE, self.ago(minutes=5), now=self.now).status, "not_earlier")
            intake_state.acquire_lease(SITE, self.now)
            running = intake_state.rescan_since(SITE, self.ago(days=1), now=self.now)
            IntakeState.objects.filter(mailbox=SITE).update(lease_until=None, lease_token=None, paused=True)
            moved = intake_state.rescan_since(SITE, self.ago(days=1), actor=staff, now=self.now)

        self.assertEqual((running.status, running.previous), ("running", self.ago(minutes=10)))
        self.assertEqual((moved.status, moved.previous, moved.paused), ("moved", self.ago(minutes=10), True))
        self.assertEqual((row().checkpoint_at, row().paused), (self.ago(days=1), True))
        self.assertIn("Rescan since", LogEntry.objects.get().change_message)
        self.assertFalse(EmailMonitorState.objects.exists())
        self.assertEqual(str(row()), f"Helpdesk intake for {SITE}")

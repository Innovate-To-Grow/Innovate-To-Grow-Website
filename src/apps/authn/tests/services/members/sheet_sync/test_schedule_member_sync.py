from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.authn.models import Member
from apps.authn.services.members.sheet_sync import (
    _build_row,
    _safe,
)
from apps.authn.tests.services.members.sheet_sync.test_member_sheet_sync import _create_member, _enable_config
from apps.core.models import BackgroundJob


class ScheduleMemberSyncTests(TestCase):
    def test_noop_when_not_configured(self):
        from apps.authn.services.members.sheet_sync import schedule_member_sync

        schedule_member_sync()  # should not raise

        self.assertFalse(BackgroundJob.objects.exists())

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_noop_when_auto_sync_disabled(self):
        _enable_config(auto_sync=False)

        from apps.authn.services.members.sheet_sync import schedule_member_sync

        schedule_member_sync()

        self.assertFalse(BackgroundJob.objects.exists())

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_enqueues_durable_job_when_configured(self):
        _enable_config()

        from apps.authn.services.members.sheet_sync import schedule_member_sync

        schedule_member_sync()

        self.assertTrue(
            BackgroundJob.objects.filter(
                kind="authn.member_sheet_sync",
                status=BackgroundJob.Status.PENDING,
            ).exists()
        )

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    @patch("apps.authn.services.members.sheet_sync.scheduler._schedule_in_process_sync")
    def test_rollout_fallback_schedules_nonblocking_debounce(self, schedule):
        _enable_config()

        from apps.authn.services.members.sheet_sync import schedule_member_sync

        schedule_member_sync()

        schedule.assert_called_once_with(delay=15)

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    @patch("apps.authn.services.members.sheet_sync.scheduler.threading.Timer")
    def test_rollout_timer_start_failure_is_logged_and_suppressed(self, timer_class):
        from apps.authn.services.members.sheet_sync import scheduler

        _enable_config()
        scheduler._sync_timer = None
        timer_class.return_value.start.side_effect = RuntimeError("can't start new thread")

        with self.assertLogs(scheduler.logger, level="ERROR"):
            scheduler.schedule_member_sync()

        self.assertIsNone(scheduler._sync_timer)

    @patch("apps.authn.services.members.sheet_sync.scheduler.threading.Timer")
    def test_rollout_timer_replaces_and_cancels_previous_debounce(self, timer_class):
        from apps.authn.services.members.sheet_sync import scheduler

        previous = MagicMock()
        scheduler._sync_timer = previous
        self.addCleanup(setattr, scheduler, "_sync_timer", None)

        scheduler._schedule_in_process_sync(delay=3)

        timer = timer_class.return_value
        previous.cancel.assert_called_once_with()
        timer_class.assert_called_once_with(3, scheduler._run_in_process_sync)
        self.assertIs(scheduler._sync_timer, timer)
        self.assertTrue(timer.daemon)
        timer.start.assert_called_once_with()

    def test_stale_rollout_timer_cannot_clear_or_run_newer_debounce(self):
        from apps.authn.services.members.sheet_sync import scheduler

        stale_timer = MagicMock()
        current_timer = MagicMock()
        scheduler._sync_timer = current_timer
        self.addCleanup(setattr, scheduler, "_sync_timer", None)

        with (
            patch.object(scheduler.threading, "current_thread", return_value=stale_timer),
            patch.object(scheduler, "_flush_pending_sync") as flush,
            patch.object(scheduler, "close_old_connections") as close_connections,
        ):
            scheduler._run_in_process_sync()

        self.assertIs(scheduler._sync_timer, current_timer)
        flush.assert_not_called()
        close_connections.assert_not_called()

    def test_current_rollout_timer_clears_cache_and_refreshes_connections(self):
        from apps.authn.services.members.sheet_sync import scheduler

        current_timer = MagicMock()
        scheduler._sync_timer = current_timer
        self.addCleanup(setattr, scheduler, "_sync_timer", None)

        with (
            patch.object(scheduler.threading, "current_thread", return_value=current_timer),
            patch.object(scheduler, "_flush_pending_sync") as flush,
            patch.object(scheduler, "close_old_connections") as close_connections,
        ):
            scheduler._run_in_process_sync()

        self.assertIsNone(scheduler._sync_timer)
        flush.assert_called_once_with()
        self.assertEqual(close_connections.call_count, 2)


class FormulaInjectionTests(TestCase):
    def test_safe_passes_through_plain_text(self):
        self.assertEqual(_safe("Alice"), "Alice")
        self.assertEqual(_safe(""), "")
        self.assertEqual(_safe(None), "")

    def test_safe_escapes_each_trigger(self):
        for trigger in ("=", "+", "-", "@", "\t", "\r"):
            payload = f"{trigger}HACK()"
            self.assertEqual(_safe(payload), f"'{payload}", f"trigger {trigger!r} not escaped")

    def test_build_row_escapes_formula_in_first_name(self):
        member = _create_member(first='=HYPERLINK("https://evil/","x")')
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertTrue(row[1].startswith("'="))

    def test_build_row_escapes_formula_in_organization(self):
        member = _create_member(org="@SUM(A1:A10)")
        member = Member.objects.prefetch_related("contact_emails", "contact_phones").get(pk=member.pk)
        row = _build_row(member)
        self.assertTrue(row[6].startswith("'@"))

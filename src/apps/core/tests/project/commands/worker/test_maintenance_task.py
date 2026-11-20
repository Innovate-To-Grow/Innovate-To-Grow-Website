from django.test import SimpleTestCase

from apps.core.management.commands import run_background_worker
from apps.core.tests.project.commands.worker.test_run_background_worker import (
    HELPDESK_NOTHING_PURGED,
    LOGGER_NAME,
    MAINTENANCE_SERVICES,
    NO_IMPORTS_PURGED,
    NOTHING_CLEANED,
    NOTHING_COUNTED,
    NOTHING_MAINTAINED,
    assert_each_service_ran_once,
    patch_maintenance,
)


class _MaintenanceTaskCase(SimpleTestCase):
    def run_patched(self, **side_effects):
        patchers = patch_maintenance(**side_effects)
        mocks = {}
        for name, patcher in zip(MAINTENANCE_SERVICES, patchers, strict=True):
            mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        run_background_worker.run_maintenance()
        return mocks


class MaintenanceTaskTests(_MaintenanceTaskCase):
    def test_tasks_run_once_each_in_declared_order(self):
        calls = []

        def record(name, result):
            return lambda **_kwargs: calls.append(name) or result

        self.run_patched(
            purge_retired_auth_keypairs=record("keys", 0),
            purge_expired_public_assistant_budgets=record("assistant budgets", 0),
            cleanup_expired_records=record("send verification", NOTHING_CLEANED),
            clear_expired_sessions=record("sessions", 0),
            purge_expired_failure_windows=record("login failure windows", 0),
            purge_member_imports=record("member imports", NO_IMPORTS_PURGED),
            run_delivery_rate_maintenance=record("delivery rates", NOTHING_MAINTAINED),
            active_certificate_expiry=record("graph certificate", None),
            ensure_bounce_scan_scheduled=record("bounce scans", False),
            ensure_delivery_trace_scheduled=record("delivery traces", False),
            count_bounced_addresses=record("bounced addresses", NOTHING_COUNTED),
            refresh_bounced_address_links=record("bounced address links", 0),
            sync_sms_opt_outs=record("sms opt-outs", None),
            purge_expired_email_telemetry=record("email telemetry", {"emails": 0, "bounces": 0}),
            purge_expired_inbound_queue=record("inbound queue", 0),
            purge_finished_bounce_scans=record("bounce scan jobs", 0),
            purge_finished_delivery_traces=record("delivery trace jobs", 0),
            ensure_helpdesk_intake_scheduled=record("helpdesk intake", False),
            ensure_helpdesk_ingest_scheduled=record("helpdesk ingest", False),
            purge_expired_helpdesk=record("helpdesk retention", HELPDESK_NOTHING_PURGED),
            purge_finished_helpdesk_ingests=record("helpdesk ingest jobs", 0),
            purge_finished_helpdesk_intake_scans=record("helpdesk intake scans", 0),
            ensure_inbox_poll_scheduled=record("inbox poll", False),
            purge_finished_inbox_polls=record("inbox poll jobs", 0),
        )

        self.assertEqual(
            calls,
            [
                "keys",
                "assistant budgets",
                "send verification",
                "sessions",
                "login failure windows",
                "member imports",
                "delivery rates",
                "graph certificate",
                "bounce scans",
                "delivery traces",
                "bounced addresses",
                "bounced address links",
                "sms opt-outs",
                "email telemetry",
                "inbound queue",
                "bounce scan jobs",
                "delivery trace jobs",
                "helpdesk intake",
                "helpdesk ingest",
                "helpdesk retention",
                "helpdesk ingest jobs",
                "helpdesk intake scans",
                "inbox poll",
                "inbox poll jobs",
            ],
        )
        self.assertEqual(
            [name for name, _task in run_background_worker.MAINTENANCE_TASKS],
            [
                "Retired RSA key purge",
                "Public assistant budget purge",
                "Send verification cleanup",
                "Expired session cleanup",
                "Login failure window purge",
                "Member import purge",
                "Delivery-rate maintenance",
                "Microsoft Graph certificate expiry check",
                "Email bounce scan scheduling",
                "Email delivery trace scheduling",
                "Bounced address counting",
                "SMS opt-out sync",
                "Email telemetry retention",
                "Helpdesk intake scheduling",
                "Helpdesk ingest scheduling",
                "Helpdesk retention",
                "Inbox poll scheduling",
            ],
        )

    def test_a_failing_task_is_logged_and_every_other_task_still_runs(self):
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            mocks = self.run_patched(
                purge_retired_auth_keypairs=RuntimeError("key store unavailable"),
                cleanup_expired_records=RuntimeError("database temporarily unavailable"),
                clear_expired_sessions=lambda **_kwargs: 3,
            )

        assert_each_service_ran_once(self, mocks)
        self.assertEqual(
            [(record.levelname, record.getMessage(), bool(record.exc_info)) for record in logs.records],
            [
                ("ERROR", "Retired RSA key purge failed", True),
                ("ERROR", "Send verification cleanup failed", True),
                ("INFO", "Cleared 3 expired sessions", False),
            ],
        )

    def test_member_import_purge_logs_its_counts_only_when_it_purged_something(self):
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            mocks = self.run_patched(purge_member_imports=lambda **_kwargs: {"expired": 2, "blanked": 1, "deleted": 0})

        mocks["purge_member_imports"].assert_called_once_with(should_stop=None)
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["Member import retention: deleted 2 expired and 0 old imports; blanked 1"],
        )

    def test_a_failing_login_window_purge_is_isolated(self):
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            mocks = self.run_patched(
                clear_expired_sessions=lambda **_kwargs: 3,
                purge_expired_failure_windows=RuntimeError("database temporarily unavailable"),
            )

        assert_each_service_ran_once(self, mocks)
        self.assertEqual(
            [(record.levelname, record.getMessage(), bool(record.exc_info)) for record in logs.records],
            [
                ("INFO", "Cleared 3 expired sessions", False),
                ("ERROR", "Login failure window purge failed", True),
            ],
        )

    def test_login_window_purge_runs_after_earlier_failures_and_logs_its_count(self):
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            mocks = self.run_patched(
                purge_retired_auth_keypairs=RuntimeError("key store unavailable"),
                clear_expired_sessions=RuntimeError("session table locked"),
                purge_expired_failure_windows=lambda **_kwargs: 4,
            )

        mocks["purge_expired_failure_windows"].assert_called_once_with(should_stop=None)
        self.assertEqual(
            [(record.levelname, record.getMessage()) for record in logs.records],
            [
                ("ERROR", "Retired RSA key purge failed"),
                ("ERROR", "Expired session cleanup failed"),
                ("INFO", "Purged 4 expired login failure windows"),
            ],
        )

    def test_counts_are_logged_only_when_something_was_cleaned(self):
        cleaned = {"expired_challenges": 2, "deleted_challenges": 3, "deleted_requests": 4}
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            self.run_patched(cleanup_expired_records=lambda **_kwargs: cleaned)

        self.assertEqual(
            logs.output,
            [
                f"INFO:{LOGGER_NAME}:Send verification cleanup: expired 2 challenges; deleted 3 challenges "
                "and 4 send requests"
            ],
        )
        with self.assertNoLogs(LOGGER_NAME, level="INFO"):
            self.run_patched()

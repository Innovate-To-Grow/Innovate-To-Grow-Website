from io import StringIO
from unittest.mock import patch

from apps.core.management.commands import run_background_worker
from apps.core.tests.project.commands.worker.test_maintenance_task import _MaintenanceTaskCase
from apps.core.tests.project.commands.worker.test_run_background_worker import (
    HELPDESK_NOTHING_PURGED,
    LOGGER_NAME,
    MAINTENANCE_SERVICES,
    assert_each_service_ran_once,
    patch_maintenance,
)


class MaintenanceTaskTests(_MaintenanceTaskCase):
    def test_the_helpdesk_counts_name_its_intake_scans_and_scheduling_is_logged_at_debug(self):
        purged = {**HELPDESK_NOTHING_PURGED, "tickets": 2}
        with self.assertLogs(LOGGER_NAME, level="DEBUG") as logs:
            self.run_patched(
                ensure_helpdesk_intake_scheduled=lambda **_kwargs: True,
                ensure_helpdesk_ingest_scheduled=lambda **_kwargs: True,
                purge_expired_helpdesk=lambda **_kwargs: purged,
                purge_finished_helpdesk_intake_scans=lambda **_kwargs: 4,
            )

        self.assertIn(f"DEBUG:{LOGGER_NAME}:Queued a helpdesk intake scan", logs.output)
        self.assertIn(f"DEBUG:{LOGGER_NAME}:Queued a helpdesk ingest run", logs.output)
        self.assertIn(
            f"INFO:{LOGGER_NAME}:Helpdesk retention: purged 0 automated, 0 spam and 0 closed-ticket bodies and 0 "
            "attachments; deleted 2 tickets, 0 finished ingest jobs and 4 finished intake scans",
            logs.output,
        )

    def test_bounced_address_counts_are_logged_only_when_something_changed(self):
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            self.run_patched(
                count_bounced_addresses=lambda **_kwargs: {"graph": 3, "ses": 1, "inbound": 2, "busy": False},
                refresh_bounced_address_links=lambda **_kwargs: 2,
            )

        self.assertEqual(
            logs.output,
            [
                f"INFO:{LOGGER_NAME}:Bounced addresses: counted 3 bounce reports, 1 SES events and 2 "
                "left-the-organisation notices; refreshed 2 addresses"
            ],
        )

    def test_left_the_organisation_notices_alone_are_logged_and_an_older_result_still_reads(self):
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            self.run_patched(
                count_bounced_addresses=lambda **_kwargs: {"graph": 0, "ses": 0, "inbound": 1, "busy": False},
                refresh_bounced_address_links=lambda **_kwargs: 0,
            )
        with self.assertLogs(LOGGER_NAME, level="INFO") as older:
            self.run_patched(
                count_bounced_addresses=lambda **_kwargs: {"graph": 1, "ses": 0, "busy": False},
                refresh_bounced_address_links=lambda **_kwargs: 0,
            )

        self.assertEqual(
            logs.output,
            [
                f"INFO:{LOGGER_NAME}:Bounced addresses: counted 0 bounce reports, 0 SES events and 1 "
                "left-the-organisation notices; refreshed 0 addresses"
            ],
        )
        self.assertIn("counted 1 bounce reports, 0 SES events and 0 left-the-organisation notices", older.output[0])

    def test_a_stop_request_skips_the_remaining_tasks(self):
        ran = []
        tasks = (
            ("first", lambda _should_stop: ran.append("first")),
            ("second", lambda _should_stop: ran.append("second")),
        )

        run_background_worker.run_maintenance(tasks, should_stop=lambda: bool(ran))

        self.assertEqual(ran, ["first"])

    def test_every_task_is_handed_the_stop_check(self):
        received = []
        tasks = (("first", received.append), ("second", received.append))

        def should_stop():
            return False

        run_background_worker.run_maintenance(tasks, should_stop=should_stop)

        self.assertEqual(received, [should_stop, should_stop])

    def test_the_batched_services_receive_the_workers_stop_check(self):
        patchers = patch_maintenance()
        mocks = {}
        for name, patcher in zip(MAINTENANCE_SERVICES, patchers, strict=True):
            mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

        def should_stop():
            return False

        run_background_worker.run_maintenance(should_stop=should_stop)

        assert_each_service_ran_once(self, mocks, should_stop=should_stop)

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1})
    @patch.object(run_background_worker, "claim_jobs", return_value=[])
    @patch.object(run_background_worker, "recover_stale_jobs")
    @patch.object(run_background_worker, "schedule_startup_reconciliation")
    def test_the_worker_cycle_survives_every_task_failing(self, _startup, _recover, claim, _metrics, publish):
        for patcher in patch_maintenance(
            purge_retired_auth_keypairs=RuntimeError("a"),
            purge_expired_public_assistant_budgets=RuntimeError("b"),
            cleanup_expired_records=RuntimeError("c"),
            clear_expired_sessions=RuntimeError("d"),
            purge_expired_failure_windows=RuntimeError("e"),
            purge_member_imports=RuntimeError("j"),
            run_delivery_rate_maintenance=RuntimeError("g"),
            active_certificate_expiry=RuntimeError("f"),
            ensure_bounce_scan_scheduled=RuntimeError("h"),
            ensure_delivery_trace_scheduled=RuntimeError("t"),
            count_bounced_addresses=RuntimeError("j"),
            sync_sms_opt_outs=RuntimeError("k"),
            purge_expired_email_telemetry=RuntimeError("i"),
            ensure_helpdesk_intake_scheduled=RuntimeError("l"),
            ensure_helpdesk_ingest_scheduled=RuntimeError("j"),
            purge_expired_helpdesk=RuntimeError("k"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        with self.assertLogs(LOGGER_NAME, level="ERROR") as logs:
            run_background_worker.Command(stdout=StringIO()).handle(
                once=True, batch_size=1, poll_seconds=0.25, stale_minutes=10, key_purge_seconds=3600
            )

        self.assertEqual(len(logs.output), len(run_background_worker.MAINTENANCE_TASKS))
        claim.assert_called_once_with(batch_size=1)
        publish.assert_called_once_with({"heartbeat": 1})

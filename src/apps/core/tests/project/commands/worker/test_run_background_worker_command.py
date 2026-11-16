from io import StringIO
from types import SimpleNamespace
from unittest.mock import call, patch

from django.test import SimpleTestCase

from apps.core.management.commands import run_background_worker
from apps.core.services.background_jobs import JobOutcome
from apps.core.tests.project.commands.worker.test_run_background_worker import MAINTENANCE_SERVICES, patch_worker


class RunBackgroundWorkerCommandTests(SimpleTestCase):
    def _run_once(self, *, purged_row_count=0, purged_budget_count=0, batch_size=10):
        command = run_background_worker.Command(stdout=StringIO())
        # Every maintenance service in MAINTENANCE_SERVICES (below) is patched: a new service needs no change here.
        returns = {
            **MAINTENANCE_SERVICES,
            "purge_retired_auth_keypairs": purged_row_count,
            "purge_expired_public_assistant_budgets": purged_budget_count,
            "schedule_startup_reconciliation": False,
        }
        with patch_worker(returns) as mocks:
            command.handle(
                once=True,
                batch_size=batch_size,
                poll_seconds=0.25,
                stale_minutes=10,
                key_purge_seconds=3600,
            )
        return mocks["purge_retired_auth_keypairs"], mocks["purge_expired_public_assistant_budgets"]

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1})
    @patch.object(run_background_worker, "claim_jobs", return_value=[])
    @patch.object(run_background_worker, "recover_stale_jobs")
    def test_worker_runs_retired_key_purge_maintenance(
        self,
        _recover,
        _claim,
        _metrics,
        _publish,
    ):
        with self.assertLogs(run_background_worker.logger, level="INFO") as logs:
            purge, budget_purge = self._run_once(purged_row_count=2)

        purge.assert_called_once_with()
        budget_purge.assert_called_once_with()
        self.assertEqual(
            logs.output, ["INFO:apps.core.management.commands.run_background_worker:Purged retired RSA keypair rows"]
        )

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1})
    @patch.object(run_background_worker, "claim_jobs", return_value=[])
    @patch.object(run_background_worker, "recover_stale_jobs")
    def test_worker_purges_expired_public_assistant_budgets(
        self,
        _recover,
        _claim,
        _metrics,
        _publish,
    ):
        with self.assertLogs(run_background_worker.logger, level="INFO") as logs:
            purge, budget_purge = self._run_once(purged_budget_count=2)

        purge.assert_called_once_with()
        budget_purge.assert_called_once_with()
        self.assertEqual(
            logs.output,
            ["INFO:apps.core.management.commands.run_background_worker:Purged expired public assistant budget rows"],
        )

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(
        run_background_worker,
        "worker_metrics",
        side_effect=RuntimeError("metrics unavailable"),
    )
    @patch.object(run_background_worker, "claim_jobs", return_value=[])
    @patch.object(run_background_worker, "recover_stale_jobs")
    def test_metrics_failure_does_not_terminate_once_cycle(
        self,
        _recover,
        _claim,
        _metrics,
        publish,
    ):
        self._run_once()

        publish.assert_not_called()

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1})
    @patch.object(run_background_worker, "run_claimed_job")
    @patch.object(
        run_background_worker,
        "claim_jobs",
        side_effect=[
            [SimpleNamespace(pk=1)],
            [SimpleNamespace(pk=2)],
        ],
    )
    @patch.object(run_background_worker, "recover_stale_jobs")
    def test_job_boundary_failure_does_not_skip_remaining_batch(
        self,
        _recover,
        _claim,
        process,
        _metrics,
        _publish,
    ):
        process.side_effect = [RuntimeError("mirror unavailable"), JobOutcome.SUCCEEDED]

        self._run_once(batch_size=2)

        self.assertEqual(
            process.call_args_list,
            [call(SimpleNamespace(pk=1)), call(SimpleNamespace(pk=2))],
        )
        self.assertEqual(_claim.call_args_list, [call(batch_size=1), call(batch_size=1)])

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1})
    @patch.object(run_background_worker, "run_claimed_job")
    @patch.object(
        run_background_worker,
        "claim_jobs",
        side_effect=[[SimpleNamespace(pk=1)], []],
    )
    @patch.object(run_background_worker, "recover_stale_jobs")
    def test_empty_single_job_claim_stops_the_current_batch(
        self,
        _recover,
        claim,
        process,
        _metrics,
        _publish,
    ):
        self._run_once(batch_size=5)

        process.assert_called_once_with(SimpleNamespace(pk=1))
        self.assertEqual(claim.call_args_list, [call(batch_size=1), call(batch_size=1)])

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1})
    @patch.object(run_background_worker, "claim_jobs")
    @patch.object(
        run_background_worker,
        "recover_stale_jobs",
        side_effect=RuntimeError("database temporarily unavailable"),
    )
    def test_maintenance_failure_does_not_terminate_cycle(
        self,
        _recover,
        claim,
        _metrics,
        publish,
    ):
        self._run_once()

        claim.assert_not_called()
        publish.assert_called_once_with({"heartbeat": 1})

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.cms.models import CMSPage, RouteRedirect
from apps.cms.services.amplify import amplify_redirects as amplify_redirect_service
from apps.cms.services.amplify.amplify_redirects import (
    AMPLIFY_CONFIGURATION_PAYLOAD_KEY,
    AMPLIFY_REDIRECT_JOB_KIND,
    AmplifyRedirectConfigurationError,
    amplify_source_variants,
    canonical_amplify_base_rules,
    get_amplify_redirect_sync_status,
    merge_amplify_rules,
    reconcile_amplify_redirects,
    schedule_amplify_redirect_sync,
)
from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, process_claimed_job


def _client_error(code: str, status_code: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "provider detail must not leak"},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        },
        "UpdateApp",
    )


def _base_rules(*, proxy_admin_paths: bool = False):
    return canonical_amplify_base_rules(
        backend_proxy_url="https://api.example",
        proxy_admin_paths=proxy_admin_paths,
    )


class AmplifyRuleMergeTests(SimpleTestCase):
    def test_source_variants_preserve_case_and_add_trailing_slash(self):
        self.assertEqual(amplify_source_variants("/FAQs"), ("/FAQs", "/FAQs/"))
        self.assertEqual(amplify_source_variants("/"), ("/",))

    def test_merge_replaces_owned_rules_and_preserves_unmanaged_order(self):
        fallback = {
            "source": "</^[^.]+$/>",
            "target": "/index.html",
            "status": "200",
        }
        existing = [
            {"source": "/api/<*>", "target": "https://api.example/<*>", "status": "200"},
            {"source": "/Old", "target": "/stale", "status": "301"},
            {"source": "/Old/", "target": "/stale", "status": "301"},
            {"source": "/inactive", "target": "/stale", "status": "301"},
            fallback,
            {"source": "/asset", "target": "/asset.html", "status": "200"},
        ]

        desired, active_count, managed_count = merge_amplify_rules(
            existing_rules=existing,
            all_redirects=[
                {"source_path": "/Old", "destination_path": "/new", "is_active": True},
                {
                    "source_path": "/inactive",
                    "destination_path": "/new",
                    "is_active": False,
                    "edge_rule_managed": True,
                },
            ],
        )

        self.assertEqual(active_count, 1)
        self.assertEqual(managed_count, 2)
        self.assertEqual(
            desired,
            [
                existing[0],
                {"source": "/Old", "target": "/new", "status": "301"},
                {"source": "/Old/", "target": "/new", "status": "301"},
                fallback,
                existing[-1],
            ],
        )

    def test_never_active_inactive_redirect_does_not_claim_manual_rule(self):
        manual_rule = {"source": "/inactive", "target": "/manual", "status": "302"}

        desired, active_count, managed_count = merge_amplify_rules(
            existing_rules=[manual_rule],
            all_redirects=[
                {
                    "source_path": "/inactive",
                    "destination_path": "/new",
                    "is_active": False,
                    "edge_rule_managed": False,
                    "edge_sync_attempted_at": "historical-attempt",
                    "edge_synced_at": "historical-success",
                },
            ],
        )

        self.assertEqual(desired, [manual_rule])
        self.assertEqual(active_count, 0)
        self.assertEqual(managed_count, 0)

    def test_canonical_base_rules_replace_stale_owned_rules_and_keep_spa_last(self):
        manual_rule = {"source": "/robots.txt", "target": "/robots-prod.txt", "status": "200"}
        stale_fallback = {"source": "/<*>", "target": "/index.html", "status": "404-200"}

        desired, active_count, managed_count = merge_amplify_rules(
            existing_rules=[
                {"source": "/sitemap.xml", "target": "https://old.example/sitemap.xml", "status": "200"},
                {"source": "/api/<*>", "target": "https://old.example/<*>", "status": "200"},
                {"source": "/admin/<*>", "target": "https://old.example/admin/<*>", "status": "200"},
                manual_rule,
                stale_fallback,
            ],
            all_redirects=[
                {
                    "source_path": "/Legacy",
                    "destination_path": "/target",
                    "is_active": True,
                    "edge_rule_managed": False,
                }
            ],
            base_rules=_base_rules(),
        )

        self.assertEqual(active_count, 1)
        self.assertEqual(managed_count, 2)
        self.assertEqual(
            desired,
            [
                *_base_rules()[:-1],
                {"source": "/Legacy", "target": "/target", "status": "301"},
                {"source": "/Legacy/", "target": "/target", "status": "301"},
                manual_rule,
                _base_rules()[-1],
            ],
        )

    def test_literal_index_rewrite_is_preserved_as_an_unrelated_rule(self):
        literal_rewrite = {
            "source": "/standalone-shell",
            "target": "/index.html",
            "status": "200",
        }

        desired, _active_count, _managed_count = merge_amplify_rules(
            existing_rules=[literal_rewrite],
            all_redirects=[],
            base_rules=_base_rules(),
        )

        self.assertEqual(desired, [*_base_rules()[:-1], literal_rewrite, _base_rules()[-1]])

    def test_partial_regex_index_rewrite_is_preserved_as_an_unrelated_rule(self):
        partial_regex_rewrite = {
            "source": r"</^/campaign/.+$/>",
            "target": "/index.html",
            "status": "200",
        }

        desired, _active_count, _managed_count = merge_amplify_rules(
            existing_rules=[partial_regex_rewrite],
            all_redirects=[],
            base_rules=_base_rules(),
        )

        self.assertEqual(desired, [*_base_rules()[:-1], partial_regex_rewrite, _base_rules()[-1]])

    def test_exact_redirects_precede_preserved_wildcard_rules(self):
        broad_rule = {"source": "/legacy/<*>", "target": "/legacy-shell", "status": "200"}

        desired, _active_count, _managed_count = merge_amplify_rules(
            existing_rules=[broad_rule],
            all_redirects=[
                {
                    "source_path": "/legacy/specific",
                    "destination_path": "/target",
                    "is_active": True,
                    "edge_rule_managed": False,
                }
            ],
            base_rules=_base_rules(),
        )

        self.assertEqual(
            desired,
            [
                *_base_rules()[:-1],
                {"source": "/legacy/specific", "target": "/target", "status": "301"},
                {"source": "/legacy/specific/", "target": "/target", "status": "301"},
                broad_rule,
                _base_rules()[-1],
            ],
        )

    def test_admin_proxy_setting_adds_all_reserved_backend_routes(self):
        rules = _base_rules(proxy_admin_paths=True)

        self.assertEqual(
            [rule["source"] for rule in rules],
            [
                "/sitemap.xml",
                "/api/<*>",
                "/admin",
                "/admin/<*>",
                "/static/<*>",
                "/media/<*>",
                rules[-1]["source"],
            ],
        )
        self.assertEqual(rules[2]["target"], "https://api.example/admin/")
        self.assertEqual(rules[-1]["target"], "/index.html")

    def test_postgres_scheduler_uses_transaction_advisory_lock(self):
        database = MagicMock()
        database.vendor = "postgresql"
        cursor = database.cursor.return_value.__enter__.return_value

        with patch.object(amplify_redirect_service, "connection", database):
            with amplify_redirect_service._serialize_scheduling():
                pass

        cursor.execute.assert_called_once_with(
            "SELECT pg_advisory_xact_lock(%s)",
            [amplify_redirect_service._AMPLIFY_SCHEDULE_LOCK_ID],
        )


class AmplifySingleWriterWorkflowTests(SimpleTestCase):
    def test_frontend_deploy_does_not_write_the_full_amplify_rule_list(self):
        repository_root = Path(__file__).resolve().parents[5]
        workflow = (repository_root / ".github/workflows/deploy-frontend.yml").read_text(encoding="utf-8")

        self.assertNotIn('"get-app"', workflow)
        self.assertNotIn('"update-app"', workflow)
        self.assertNotIn("aws amplify update-app", workflow)
        self.assertIn("aws amplify create-deployment", workflow)
        self.assertIn("aws amplify start-deployment", workflow)


@override_settings(
    BACKGROUND_JOBS_ENABLED=False,
    AMPLIFY_BACKEND_PROXY_URL="https://api.example",
    AMPLIFY_PROXY_ADMIN_PATHS=False,
)
class AmplifyReconcileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CMSPage.objects.create(
            slug="redirect-target",
            route="/target",
            title="Redirect target",
            status="published",
        )
        cls.active = RouteRedirect.objects.create(
            source_path="/Legacy",
            destination_path="/target",
            is_active=True,
        )
        cls.inactive = RouteRedirect.objects.create(
            source_path="/retired",
            destination_path="/target",
            is_active=False,
        )
        RouteRedirect.objects.filter(pk=cls.inactive.pk).update(
            edge_rule_managed=True,
            edge_sync_attempted_at=timezone.now(),
            edge_synced_at=timezone.now(),
        )

    @override_settings(AMPLIFY_APP_ID="app-123", AWS_REGION="us-west-2")
    def test_reconcile_updates_changed_rules_before_spa_fallback(self):
        client = MagicMock()
        fallback = {"source": "</^[^.]+$/>", "target": "/index.html", "status": "200"}
        client.get_app.return_value = {
            "app": {
                "customRules": [
                    {"source": "/api/<*>", "target": "https://api.example/<*>", "status": "200"},
                    {"source": "/Legacy", "target": "/wrong", "status": "301"},
                    {"source": "/retired/", "target": "/wrong", "status": "301"},
                    fallback,
                ]
            }
        }

        result = reconcile_amplify_redirects(client=client)

        self.assertTrue(result.changed)
        self.assertEqual(result.active_redirect_count, 1)
        self.assertEqual(result.managed_rule_count, 2)
        self.active.refresh_from_db()
        self.inactive.refresh_from_db()
        self.assertTrue(self.active.edge_rule_managed)
        self.assertFalse(self.inactive.edge_rule_managed)
        client.get_app.assert_called_once_with(appId="app-123")
        client.update_app.assert_called_once_with(
            appId="app-123",
            customRules=[
                *_base_rules()[:-1],
                {"source": "/Legacy", "target": "/target", "status": "301"},
                {"source": "/Legacy/", "target": "/target", "status": "301"},
                _base_rules()[-1],
            ],
        )

    @override_settings(AMPLIFY_APP_ID="app-123", AWS_REGION="us-west-2")
    def test_reconcile_is_idempotent(self):
        client = MagicMock()
        client.get_app.return_value = {
            "app": {
                "customRules": [
                    *_base_rules()[:-1],
                    {"source": "/Legacy", "target": "/target", "status": "301"},
                    {"source": "/Legacy/", "target": "/target", "status": "301"},
                    _base_rules()[-1],
                ]
            }
        }

        result = reconcile_amplify_redirects(client=client)

        self.assertFalse(result.changed)
        client.update_app.assert_not_called()
        self.active.refresh_from_db()
        self.assertTrue(self.active.edge_rule_managed)

    @override_settings(AMPLIFY_APP_ID="app-123", AMPLIFY_BACKEND_PROXY_URL="")
    def test_reconcile_requires_backend_proxy_url_before_provider_io(self):
        client = MagicMock()

        with self.assertRaisesMessage(
            AmplifyRedirectConfigurationError,
            "AMPLIFY_BACKEND_PROXY_URL must be an absolute HTTP(S) URL",
        ):
            reconcile_amplify_redirects(client=client)

        client.get_app.assert_not_called()
        client.update_app.assert_not_called()

    @override_settings(AMPLIFY_APP_ID="")
    def test_reconcile_requires_app_id_without_creating_a_client(self):
        with patch("apps.cms.services.amplify.amplify_redirects.boto3.client") as client:
            with self.assertRaisesMessage(
                AmplifyRedirectConfigurationError,
                "AMPLIFY_APP_ID is not configured",
            ):
                reconcile_amplify_redirects()
        client.assert_not_called()


@override_settings(
    AMPLIFY_APP_ID="app-123",
    AMPLIFY_BACKEND_PROXY_URL="https://api.example",
    AMPLIFY_PROXY_ADMIN_PATHS=False,
    BACKGROUND_JOBS_ENABLED=False,
)
class AmplifyOwnershipLifecycleTests(TestCase):
    def setUp(self):
        CMSPage.objects.create(
            slug="ownership-target",
            route="/ownership-target",
            title="Ownership target",
            status="published",
        )
        self.redirect = RouteRedirect.objects.create(
            source_path="/ownership-legacy",
            destination_path="/ownership-target",
            is_active=True,
        )

    def test_denied_never_synced_deactivation_preserves_manual_rule(self):
        manual_rule = {"source": "/ownership-legacy", "target": "/manual", "status": "302"}
        denied_client = MagicMock()
        denied_client.get_app.return_value = {"app": {"customRules": [manual_rule]}}
        denied_client.update_app.side_effect = _client_error("AccessDeniedException", 403)

        with self.assertRaises(ClientError):
            reconcile_amplify_redirects(client=denied_client)

        self.redirect.refresh_from_db()
        self.assertFalse(self.redirect.edge_rule_managed)
        self.redirect.is_active = False
        self.redirect.save(update_fields=["is_active", "updated_at"])

        cleanup_client = MagicMock()
        cleanup_client.get_app.return_value = {
            "app": {"customRules": [*_base_rules()[:-1], manual_rule, _base_rules()[-1]]}
        }
        result = reconcile_amplify_redirects(client=cleanup_client)

        self.assertFalse(result.changed)
        cleanup_client.update_app.assert_not_called()
        self.redirect.refresh_from_db()
        self.assertFalse(self.redirect.edge_rule_managed)

    def test_successful_deactivation_cleanup_clears_ownership_permanently(self):
        create_client = MagicMock()
        create_client.get_app.return_value = {"app": {"customRules": []}}

        reconcile_amplify_redirects(client=create_client)

        self.redirect.refresh_from_db()
        self.assertTrue(self.redirect.edge_rule_managed)
        submitted_rules = create_client.update_app.call_args.kwargs["customRules"]

        self.redirect.is_active = False
        self.redirect.save(update_fields=["is_active", "updated_at"])
        cleanup_client = MagicMock()
        cleanup_client.get_app.return_value = {"app": {"customRules": submitted_rules}}

        reconcile_amplify_redirects(client=cleanup_client)

        cleanup_client.update_app.assert_called_once_with(appId="app-123", customRules=_base_rules())
        self.redirect.refresh_from_db()
        self.assertFalse(self.redirect.edge_rule_managed)

        future_manual_rule = {"source": "/ownership-legacy", "target": "/future-manual", "status": "302"}
        future_client = MagicMock()
        future_client.get_app.return_value = {
            "app": {"customRules": [*_base_rules()[:-1], future_manual_rule, _base_rules()[-1]]}
        }

        result = reconcile_amplify_redirects(client=future_client)

        self.assertFalse(result.changed)
        future_client.update_app.assert_not_called()

    def test_idempotent_active_rule_is_adopted_for_later_cleanup(self):
        manual_identical_rules = [
            {"source": "/ownership-legacy", "target": "/ownership-target", "status": "301"},
            {"source": "/ownership-legacy/", "target": "/ownership-target", "status": "301"},
        ]
        client = MagicMock()
        client.get_app.return_value = {
            "app": {"customRules": [*_base_rules()[:-1], *manual_identical_rules, _base_rules()[-1]]}
        }

        result = reconcile_amplify_redirects(client=client)

        self.assertFalse(result.changed)
        self.redirect.refresh_from_db()
        self.assertTrue(self.redirect.edge_rule_managed)

        self.redirect.is_active = False
        self.redirect.save(update_fields=["is_active", "updated_at"])
        cleanup_client = MagicMock()
        cleanup_client.get_app.return_value = {
            "app": {"customRules": [*_base_rules()[:-1], *manual_identical_rules, _base_rules()[-1]]}
        }

        reconcile_amplify_redirects(client=cleanup_client)

        cleanup_client.update_app.assert_called_once_with(appId="app-123", customRules=_base_rules())
        self.redirect.refresh_from_db()
        self.assertFalse(self.redirect.edge_rule_managed)


@override_settings(AMPLIFY_APP_ID="app-123", BACKGROUND_JOBS_ENABLED=True)
class AmplifyRedirectJobTests(TestCase):
    def setUp(self):
        CMSPage.objects.create(
            slug="job-target",
            route="/job-target",
            title="Job target",
            status="published",
        )
        self.redirect = RouteRedirect.objects.create(
            source_path="/job-legacy",
            destination_path="/job-target",
            is_active=True,
        )

    def test_scheduler_coalesces_pending_jobs_and_immediate_retry_removes_delay(self):
        first = schedule_amplify_redirect_sync()
        first_requested_at = first.payload["requested_at"]
        self.assertGreater(first.available_at, timezone.now())

        second = schedule_amplify_redirect_sync(immediate=True)

        self.assertEqual(second.pk, first.pk)
        self.assertEqual(BackgroundJob.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND).count(), 1)
        self.assertLessEqual(second.available_at, timezone.now())
        self.assertNotEqual(second.payload["requested_at"], first_requested_at)

    def test_scheduler_revision_time_remains_strictly_monotonic_when_clock_is_equal(self):
        frozen_time = timezone.now()
        with patch.object(amplify_redirect_service.timezone, "now", return_value=frozen_time):
            first = schedule_amplify_redirect_sync(immediate=True)
            first_requested_at = first.payload["requested_at"]
            second = schedule_amplify_redirect_sync(immediate=True)

        self.assertGreater(
            datetime.fromisoformat(second.payload["requested_at"]),
            datetime.fromisoformat(first_requested_at),
        )

    @patch("apps.cms.services.amplify.amplify_redirects.reconcile_amplify_redirects")
    def test_successful_job_marks_redirect_synced(self, reconcile):
        job = schedule_amplify_redirect_sync(immediate=True)
        queued_configuration = job.payload[AMPLIFY_CONFIGURATION_PAYLOAD_KEY]

        self.assertTrue(process_claimed_job(claim_jobs(batch_size=1)[0]))

        self.redirect.refresh_from_db()
        self.assertEqual(self.redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.SYNCED)
        self.assertEqual(self.redirect.edge_sync_error, "")
        self.assertIsNotNone(self.redirect.edge_sync_attempted_at)
        self.assertIsNotNone(self.redirect.edge_synced_at)
        reconcile.assert_called_once_with(configuration=queued_configuration)

    @override_settings(
        AMPLIFY_CONFIG_REVISION="200.1",
        AWS_REGION="us-east-1",
        AMPLIFY_BACKEND_PROXY_URL="https://new-api.example/",
        AMPLIFY_PROXY_ADMIN_PATHS=True,
    )
    def test_job_uses_queued_configuration_during_a_rolling_deploy(self):
        job = schedule_amplify_redirect_sync(immediate=True)
        queued_configuration = job.payload[AMPLIFY_CONFIGURATION_PAYLOAD_KEY]
        self.assertEqual(
            queued_configuration,
            {
                "config_revision": "200.1",
                "app_id": "app-123",
                "region": "us-east-1",
                "backend_proxy_url": "https://new-api.example",
                "proxy_admin_paths": True,
            },
        )

        with (
            override_settings(
                AWS_REGION="us-west-2",
                AMPLIFY_BACKEND_PROXY_URL="https://old-api.example",
                AMPLIFY_PROXY_ADMIN_PATHS=False,
            ),
            patch("apps.cms.services.amplify.amplify_redirects.reconcile_amplify_redirects") as reconcile,
        ):
            self.assertTrue(process_claimed_job(claim_jobs(batch_size=1)[0]))

        reconcile.assert_called_once_with(configuration=queued_configuration)

    def test_older_web_task_carries_forward_newer_persisted_configuration(self):
        with override_settings(
            AMPLIFY_CONFIG_REVISION="300.1",
            AWS_REGION="us-east-1",
            AMPLIFY_BACKEND_PROXY_URL="https://new-api.example",
            AMPLIFY_PROXY_ADMIN_PATHS=True,
        ):
            newer = schedule_amplify_redirect_sync(immediate=True)
            newer_configuration = newer.payload[AMPLIFY_CONFIGURATION_PAYLOAD_KEY]

        with patch("apps.cms.services.amplify.amplify_redirects.reconcile_amplify_redirects"):
            self.assertTrue(process_claimed_job(claim_jobs(batch_size=1)[0]))

        with override_settings(
            AMPLIFY_CONFIG_REVISION="299.9",
            AWS_REGION="us-west-2",
            AMPLIFY_BACKEND_PROXY_URL="https://old-api.example",
            AMPLIFY_PROXY_ADMIN_PATHS=False,
        ):
            queued_by_old_web = schedule_amplify_redirect_sync(immediate=True)

        self.assertNotEqual(queued_by_old_web.pk, newer.pk)
        self.assertEqual(
            queued_by_old_web.payload[AMPLIFY_CONFIGURATION_PAYLOAD_KEY],
            newer_configuration,
        )

    @patch(
        "apps.cms.services.amplify.amplify_redirects.reconcile_amplify_redirects",
        side_effect=_client_error("ThrottlingException", 429),
    )
    def test_transient_amplify_failure_is_retried_and_visible(self, _reconcile):
        job = schedule_amplify_redirect_sync(immediate=True)

        self.assertFalse(process_claimed_job(claim_jobs(batch_size=1)[0]))

        job.refresh_from_db()
        self.redirect.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertEqual(self.redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)
        self.assertIn("temporarily unavailable", self.redirect.edge_sync_error)
        self.assertNotIn("provider detail", self.redirect.edge_sync_error)

    @patch(
        "apps.cms.services.amplify.amplify_redirects.reconcile_amplify_redirects",
        side_effect=_client_error("AccessDeniedException", 403),
    )
    def test_permanent_amplify_failure_is_marked_failed(self, _reconcile):
        job = schedule_amplify_redirect_sync(immediate=True)

        self.assertFalse(process_claimed_job(claim_jobs(batch_size=1)[0]))

        job.refresh_from_db()
        self.redirect.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertEqual(self.redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.FAILED)
        self.assertIn("rejected", self.redirect.edge_sync_error)
        self.assertNotIn("provider detail", self.redirect.edge_sync_error)

    def test_newer_edit_stays_pending_when_an_older_job_completes(self):
        schedule_amplify_redirect_sync(immediate=True)
        claimed = claim_jobs(batch_size=1)[0]
        newer_time = timezone.now() + timedelta(milliseconds=1)
        RouteRedirect.objects.filter(pk=self.redirect.pk).update(
            destination_path="/job-target",
            updated_at=newer_time,
            edge_sync_status=RouteRedirect.EdgeSyncStatus.PENDING,
        )

        with patch("apps.cms.services.amplify.amplify_redirects.reconcile_amplify_redirects"):
            self.assertTrue(process_claimed_job(claimed))

        self.redirect.refresh_from_db()
        self.assertEqual(self.redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)

    def test_older_claim_never_cancels_a_newer_requested_revision(self):
        older = schedule_amplify_redirect_sync(immediate=True)
        claimed = claim_jobs(batch_size=1)[0]
        self.assertEqual(claimed.pk, older.pk)
        newer_requested_at = timezone.now() + timedelta(milliseconds=1)
        newer = BackgroundJob.objects.create(
            kind=AMPLIFY_REDIRECT_JOB_KIND,
            dedupe_key="concurrent-newer-revision",
            payload={
                "requested_at": newer_requested_at.isoformat(),
                "requested_redirect_ids": [str(self.redirect.pk)],
            },
            available_at=timezone.now(),
        )

        with patch("apps.cms.services.amplify.amplify_redirects.reconcile_amplify_redirects") as reconcile:
            self.assertTrue(process_claimed_job(claimed))

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(older.status, BackgroundJob.Status.CANCELLED)
        reconcile.assert_not_called()
        self.assertEqual(newer.status, BackgroundJob.Status.PENDING)
        self.assertIsNone(newer.completed_at)
        self.assertEqual(newer.last_error, "")

    def test_two_processing_jobs_cannot_write_provider_revisions_in_reverse(self):
        older = schedule_amplify_redirect_sync(immediate=True)
        (older_claim,) = claim_jobs(batch_size=1)
        self.assertEqual(older_claim.pk, older.pk)

        newer = schedule_amplify_redirect_sync(immediate=True)
        (newer_claim,) = claim_jobs(batch_size=1)
        self.assertEqual(newer_claim.pk, newer.pk)

        with patch("apps.cms.services.amplify.amplify_redirects.reconcile_amplify_redirects") as reconcile:
            self.assertTrue(process_claimed_job(newer_claim))
            self.assertTrue(process_claimed_job(older_claim))

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(newer.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(older.status, BackgroundJob.Status.CANCELLED)
        reconcile.assert_called_once_with(configuration=newer.payload[AMPLIFY_CONFIGURATION_PAYLOAD_KEY])

    def test_claim_does_not_cancel_an_equal_timestamp_revision(self):
        older = schedule_amplify_redirect_sync(immediate=True)
        claimed = claim_jobs(batch_size=1)[0]
        same_timestamp = BackgroundJob.objects.create(
            kind=AMPLIFY_REDIRECT_JOB_KIND,
            dedupe_key="concurrent-equal-timestamp-revision",
            payload={
                "requested_at": older.payload["requested_at"],
                "requested_redirect_ids": [str(self.redirect.pk)],
            },
            available_at=timezone.now(),
        )

        with patch("apps.cms.services.amplify.amplify_redirects.reconcile_amplify_redirects"):
            self.assertTrue(process_claimed_job(claimed))

        same_timestamp.refresh_from_db()
        self.assertEqual(same_timestamp.status, BackgroundJob.Status.PENDING)
        self.assertIsNone(same_timestamp.completed_at)

    def test_status_helper_exposes_latest_durable_job(self):
        job = schedule_amplify_redirect_sync(immediate=True)

        status = get_amplify_redirect_sync_status()

        self.assertTrue(status["configured"])
        self.assertTrue(status["jobs_enabled"])
        self.assertEqual(status["job_id"], str(job.pk))
        self.assertEqual(status["status"], BackgroundJob.Status.PENDING)

    def test_inactive_create_invalidates_cache_without_enqueuing(self):
        cache_key = "cms:page:/signal-legacy"
        cache.set(cache_key, {"stale": True})

        with self.captureOnCommitCallbacks(execute=True):
            redirect = RouteRedirect.objects.create(
                source_path="/signal-legacy",
                destination_path="/job-target",
                is_active=False,
            )

        redirect.refresh_from_db()
        self.assertIsNone(cache.get(cache_key))
        self.assertEqual(redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)
        self.assertFalse(BackgroundJob.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND).exists())

    @patch("apps.cms.services.amplify.amplify_redirects.schedule_amplify_redirect_sync")
    def test_inactive_notes_and_destination_edits_do_not_schedule(self, schedule):
        other_target = CMSPage.objects.create(
            slug="other-job-target",
            route="/other-job-target",
            title="Other job target",
            status="published",
        )
        redirect = RouteRedirect.objects.create(
            source_path="/inactive-edit",
            destination_path="/job-target",
            is_active=False,
        )
        redirect.notes = "Documentation only"
        redirect.destination_path = other_target.route

        with self.captureOnCommitCallbacks(execute=True):
            redirect.save(update_fields=["notes", "destination_path", "updated_at"])

        schedule.assert_not_called()

    @patch("apps.cms.services.amplify.amplify_redirects.schedule_amplify_redirect_sync")
    def test_managed_inactive_edit_reschedules_pending_cleanup(self, schedule):
        redirect = RouteRedirect.objects.create(
            source_path="/managed-inactive-edit",
            destination_path="/job-target",
            is_active=False,
        )
        RouteRedirect.objects.filter(pk=redirect.pk).update(
            edge_rule_managed=True,
            edge_sync_status=RouteRedirect.EdgeSyncStatus.FAILED,
        )
        redirect.refresh_from_db()
        redirect.notes = "Retry cleanup after this edit"

        with self.captureOnCommitCallbacks(execute=True):
            redirect.save(update_fields=["notes", "updated_at"])

        redirect.refresh_from_db()
        self.assertEqual(redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)
        schedule.assert_called_once_with(redirect_ids=(redirect.pk,))

    @patch("apps.cms.services.amplify.amplify_redirects.schedule_amplify_redirect_sync")
    def test_deactivation_schedules_followup_even_before_ownership_is_confirmed(self, schedule):
        redirect = RouteRedirect.objects.create(
            source_path="/in-flight-deactivation",
            destination_path="/job-target",
            is_active=True,
        )
        self.assertFalse(redirect.edge_rule_managed)
        redirect.is_active = False

        with self.captureOnCommitCallbacks(execute=True):
            redirect.save(update_fields=["is_active", "updated_at"])

        redirect.refresh_from_db()
        self.assertEqual(redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)
        schedule.assert_called_once_with(redirect_ids=(redirect.pk,))


@override_settings(AMPLIFY_APP_ID="", BACKGROUND_JOBS_ENABLED=True)
class AmplifyUnconfiguredSchedulerTests(TestCase):
    def test_missing_app_id_leaves_redirect_pending_without_a_job(self):
        self.assertIsNone(schedule_amplify_redirect_sync(immediate=True))
        self.assertFalse(BackgroundJob.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND).exists())

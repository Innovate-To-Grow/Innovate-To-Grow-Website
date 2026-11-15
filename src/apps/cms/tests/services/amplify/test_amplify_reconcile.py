"""Reconciling Amplify redirect rules, and the ownership of rules this app wrote."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cms.models import CMSPage, RouteRedirect
from apps.cms.services.amplify import (
    AmplifyRedirectConfigurationError,
    reconcile_amplify_redirects,
)

from .amplify_helpers import _base_rules


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
        with patch("apps.cms.services.amplify.reconcile.boto3.client") as client:
            with self.assertRaisesMessage(
                AmplifyRedirectConfigurationError,
                "AMPLIFY_APP_ID is not configured",
            ):
                reconcile_amplify_redirects()
        client.assert_not_called()

from unittest.mock import MagicMock

from botocore.exceptions import ClientError
from django.test import TestCase, override_settings

from apps.cms.models import CMSPage, RouteRedirect
from apps.cms.services.amplify import (
    reconcile_amplify_redirects,
)

from .amplify_helpers import _base_rules, _client_error


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

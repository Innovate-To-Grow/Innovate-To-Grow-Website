"""Access to the System Intelligence custom admin views.

Every custom URL in ``apps.system_intelligence.admin.chat.urls`` is wrapped with ``admin.site.admin_view``, which lets
in only an Admin (an active staff member). These tests drive the real URLs through the test client to confirm:

* a signed-in regular member is sent to the admin login (302) and never reaches a view, and
* every Admin is allowed.
"""

import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig
from apps.event.tests.helpers import make_admin, make_member
from apps.system_intelligence.models import (
    ChatConversation,
    SystemIntelligenceConfig,
)


class SystemIntelligenceCustomViewGuardTests(TestCase):
    """Drive each admin_view-wrapped custom URL as a regular member and as an Admin."""

    def setUp(self):
        cache.clear()
        # AWS + chat config so any view that loads config does not blow up before
        # the guard would ever be reached on the allowed path.
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
        )
        SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            system_prompt="Use tools.",
        )
        self.denied_user = make_member(email="regular-member@example.com")
        self.allowed_user = make_admin(email="si-admin@example.com")

    def tearDown(self):
        cache.clear()

    def _convo_for(self, user):
        return ChatConversation.objects.create(created_by=user)

    # A UUID that does not need to match a real row: admin_view runs before any
    # object lookup, so a refused request never reaches the 404 branch and an
    # allowed request returns a non-redirect (404/200/405/...) before mutating.
    DUMMY_ID = "00000000-0000-0000-0000-000000000000"

    def _urls(self, conversation_id, action_id, export_id):
        """Map every guarded view name to (url, http_method)."""
        return [
            (reverse("admin:system_intelligence"), "get"),
            (reverse("admin:system_intelligence_conversations"), "get"),
            (reverse("admin:system_intelligence_new"), "post"),
            (reverse("admin:system_intelligence_usage_dashboard"), "get"),
            (reverse("admin:system_intelligence_usage_data"), "get"),
            (reverse("admin:system_intelligence_detail", args=[conversation_id]), "get"),
            (reverse("admin:system_intelligence_send", args=[conversation_id]), "post"),
            (reverse("admin:system_intelligence_command", args=[conversation_id]), "post"),
            (reverse("admin:system_intelligence_delete", args=[conversation_id]), "post"),
            (reverse("admin:system_intelligence_rename", args=[conversation_id]), "post"),
            (reverse("admin:system_intelligence_action_approve", args=[action_id]), "post"),
            (reverse("admin:system_intelligence_action_reject", args=[action_id]), "post"),
            (reverse("admin:system_intelligence_action_preview", args=[action_id]), "get"),
            (reverse("admin:system_intelligence_action_full_preview", args=[action_id]), "get"),
            (reverse("admin:system_intelligence_export_download", args=[export_id]), "get"),
        ]

    def test_a_regular_member_is_sent_to_the_admin_login_on_every_custom_view(self):
        self.client.force_login(self.denied_user)
        for url, method in self._urls(self.DUMMY_ID, self.DUMMY_ID, self.DUMMY_ID):
            with self.subTest(url=url, method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302, f"{method.upper()} {url} should redirect a member")
                self.assertIn(reverse("admin:login"), response["Location"])

    @patch(
        "apps.system_intelligence.admin.usage.dashboard.get_dashboard_context",
        return_value={"cloudwatch": {}},
    )
    def test_every_admin_is_allowed(self, _mock_dashboard_context):
        self.client.force_login(self.allowed_user)
        convo = self._convo_for(self.allowed_user)
        for url, method in self._urls(convo.id, uuid.uuid4(), uuid.uuid4()):
            with self.subTest(url=url, method=method):
                response = getattr(self.client, method)(url)
                self.assertNotIn(
                    response.status_code,
                    (302, 403),
                    f"{method.upper()} {url} should be allowed for an Admin",
                )

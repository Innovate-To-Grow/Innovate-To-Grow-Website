"""Per-app authorization guards on the System Intelligence custom admin views.

Every custom URL in ``apps.system_intelligence.admin.urls`` is wrapped with
``admin.site.admin_view``, which only enforces ``is_staff``/``is_active`` — Django
never runs the per-app model (``apps.core.access.user_can_access_app``) for a
standalone admin view. Without an explicit guard, a staff member whose
``Member.admin_apps`` lacks ``system_intelligence`` could still read these views
and trigger privileged actions. Each view now re-checks the per-app model at
entry; these tests drive the real URLs through the test client to confirm:

* a staff member granted only a *different* app gets HTTP 403, and
* a staff member granted ``system_intelligence`` (or a superuser) is allowed.
"""

import uuid

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig
from apps.event.tests.helpers import make_admin, make_superuser
from apps.system_intelligence.models import (
    ChatConversation,
    SystemIntelligenceConfig,
)


class SystemIntelligenceCustomViewGuardTests(TestCase):
    """Drive each admin_view-wrapped custom URL with mismatched/allowed access."""

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
        # Staff member WITHOUT system_intelligence access (only the cms app).
        self.denied_user = make_admin(apps=["cms"], email="cms-only@example.com")
        # Staff member WITH system_intelligence access.
        self.allowed_user = make_admin(apps=["system_intelligence"], email="si-admin@example.com")
        # I2G Master — always allowed.
        self.superuser = make_superuser(email="si-master@example.com")

    def tearDown(self):
        cache.clear()

    def _convo_for(self, user):
        return ChatConversation.objects.create(created_by=user)

    # A UUID that does not need to match a real row: the guard runs before any
    # object lookup, so a forbidden request never reaches the 404 branch and an
    # allowed request returns a non-403 (404/200/405/...) error before mutating.
    DUMMY_ID = "00000000-0000-0000-0000-000000000000"

    def _urls(self, conversation_id, action_id, export_id):
        """Map every guarded view name to (url, http_method)."""
        return [
            (reverse("admin:system_intelligence"), "get"),
            (reverse("admin:system_intelligence_debug"), "get"),
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

    def test_staff_without_app_is_forbidden_on_every_custom_view(self):
        self.client.force_login(self.denied_user)
        for url, method in self._urls(self.DUMMY_ID, self.DUMMY_ID, self.DUMMY_ID):
            with self.subTest(url=url, method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(
                    response.status_code,
                    403,
                    f"{method.upper()} {url} should be forbidden for a staff member without the app",
                )

    def test_staff_with_app_is_not_forbidden(self):
        self.client.force_login(self.allowed_user)
        convo = self._convo_for(self.allowed_user)
        for url, method in self._urls(convo.id, uuid.uuid4(), uuid.uuid4()):
            with self.subTest(url=url, method=method):
                response = getattr(self.client, method)(url)
                self.assertNotEqual(
                    response.status_code,
                    403,
                    f"{method.upper()} {url} should be allowed for a staff member with the app",
                )

    def test_superuser_is_not_forbidden(self):
        self.client.force_login(self.superuser)
        convo = self._convo_for(self.superuser)
        for url, method in self._urls(convo.id, uuid.uuid4(), uuid.uuid4()):
            with self.subTest(url=url, method=method):
                response = getattr(self.client, method)(url)
                self.assertNotEqual(
                    response.status_code,
                    403,
                    f"{method.upper()} {url} should be allowed for a superuser",
                )

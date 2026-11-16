from django.apps import apps as django_apps
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase

from apps.system_intelligence.admin.actions.lookup import (
    _changed_preview_blocks,
    _get_user_action_request,
)
from apps.system_intelligence.models import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceActionRequest,
    SystemIntelligenceConfig,
    SystemIntelligenceExport,
)
from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class ChangedPreviewBlocksTests(SimpleTestCase):
    def test_non_dict_after_blocks_are_skipped(self):
        # Line 38: an after-block that is not a dict is ignored.
        action = SystemIntelligenceActionRequest(before_snapshot={"blocks": []})
        page = {"blocks": ["not-a-dict", {"block_type": "rich_text", "id": "1"}]}
        changed = _changed_preview_blocks(action, page)
        self.assertEqual(changed, [{"block_type": "rich_text", "id": "1"}])


class GetUserActionRequestTests(SystemIntelligenceAdminBase):
    def test_missing_action_raises_permission_denied(self):
        import uuid

        request = type("R", (), {"user": self.admin_user})()
        with self.assertRaises(PermissionDenied):
            _get_user_action_request(request, uuid.uuid4())


class AppReadyIdempotencyTests(SimpleTestCase):
    def test_ready_is_idempotent_when_urls_already_patched(self):
        # Line 17: the app config has already run ready() during startup, so the
        # admin site carries the patched flag. Calling ready() again must take
        # the early-return path and leave get_urls untouched.
        app_config = django_apps.get_app_config("system_intelligence")
        self.assertTrue(getattr(admin.AdminSite, "_system_intelligence_urls_patched", False))
        before = admin.AdminSite.get_urls
        app_config.ready()
        self.assertIs(admin.AdminSite.get_urls, before)


class ModelStrTests(SystemIntelligenceAdminBase):
    def test_chat_conversation_str(self):
        # chat.py line 50.
        convo = ChatConversation.objects.create(title="Roadmap", created_by=self.admin_user)
        self.assertEqual(str(convo), f"Roadmap ({self.admin_user})")

    def test_chat_message_str_truncates_long_content(self):
        # chat.py lines 93-94 (truncating branch).
        long = "x" * 80
        message = ChatMessage.objects.create(conversation=self.conversation, role="assistant", content=long)
        self.assertEqual(str(message), f"[assistant] {'x' * 60}...")

    def test_chat_message_str_keeps_short_content(self):
        # chat.py lines 93-94 (non-truncating branch).
        message = ChatMessage.objects.create(conversation=self.conversation, role="user", content="short")
        self.assertEqual(str(message), "[user] short")

    def test_action_request_str(self):
        # actions.py line 89.
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_CREATE,
            status=SystemIntelligenceActionRequest.STATUS_PENDING,
            title="Add row",
        )
        self.assertEqual(str(action), "Database create: Add row [pending]")

    def test_export_str(self):
        # export.py line 43.
        export = SystemIntelligenceExport.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            filename="members.xlsx",
            title="Members",
            row_count=42,
        )
        self.assertEqual(str(export), "Members (42 rows)")


class ConfigModelTests(SystemIntelligenceAdminBase):
    def test_str_marks_active_config(self):
        # config.py lines 54-55 (active branch).
        config = SystemIntelligenceConfig(name="Primary", is_active=True)
        self.assertEqual(str(config), "Primary (active)")

    def test_str_omits_marker_for_inactive_config(self):
        # config.py lines 54-55 (inactive branch).
        config = SystemIntelligenceConfig(name="Backup", is_active=False)
        self.assertEqual(str(config), "Backup")

    def test_is_configured_requires_saved_active_model(self):
        self.assertFalse(SystemIntelligenceConfig().is_configured)
        config = SystemIntelligenceConfig.objects.create(
            name="Configured",
            is_active=True,
            default_model_id="model-id",
        )
        self.assertTrue(config.is_configured)

from django.contrib import admin as django_admin
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.event.tests.helpers import make_member, make_superuser
from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog


class UsageLogAdminTests(TestCase):
    def setUp(self):
        self.superuser = make_superuser(email="logadmin@example.com")
        self.member = make_member(email="subject@example.com")
        self.client.force_login(self.superuser)
        self.factory = RequestFactory()
        self.convo_admin = django_admin.site._registry[AssistantConversationLog]
        self.message_admin = django_admin.site._registry[AssistantMessageLog]

        self.convo = AssistantConversationLog.objects.create(
            source=AssistantConversationLog.SOURCE_PUBLIC_CHAT,
            session_id="55555555-5555-5555-5555-555555555555",
            ip_hash="deadbeef",
            user=self.member,
            message_count=1,
            total_tokens=15,
            last_activity_at=timezone.now(),
        )
        self.message = AssistantMessageLog.objects.create(
            conversation=self.convo,
            prompt="x" * 100,
            reply="A helpful reply.",
            status=AssistantMessageLog.STATUS_OK,
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            token_usage={"totalTokens": 15},
            latency_ms=42,
        )

    # ---- read-only --------------------------------------------------------
    def test_admins_are_read_only(self):
        request = self.factory.get("/")
        request.user = self.superuser
        for model_admin in (self.convo_admin, self.message_admin):
            self.assertFalse(model_admin.has_add_permission(request))
            self.assertFalse(model_admin.has_change_permission(request))
            self.assertFalse(model_admin.has_delete_permission(request))

    def test_inline_is_read_only(self):
        inline = self.convo_admin.inlines[0](AssistantConversationLog, django_admin.site)
        request = self.factory.get("/")
        request.user = self.superuser
        self.assertFalse(inline.has_add_permission(request, self.convo))
        self.assertEqual(inline.max_num, 0)
        self.assertFalse(inline.can_delete)

    # ---- display helpers --------------------------------------------------
    def test_conversation_display_helpers(self):
        self.assertEqual(self.convo_admin.session_short(self.convo), "55555555")
        self.assertEqual(self.convo_admin.source_badge(self.convo), ("Public Chat", "info"))
        empty = AssistantConversationLog.objects.create(
            source=AssistantConversationLog.SOURCE_AI_SEARCH, last_activity_at=timezone.now()
        )
        self.assertEqual(self.convo_admin.session_short(empty), "—")
        self.assertEqual(self.convo_admin.source_badge(empty), ("AI Search", "primary"))

    def test_message_display_helpers(self):
        self.assertEqual(self.message_admin.status_badge(self.message), ("OK", "success"))
        self.assertEqual(self.message_admin.token_total(self.message), 15)
        self.assertTrue(self.message_admin.prompt_short(self.message).endswith("..."))

    def test_inline_display_helpers(self):
        inline = self.convo_admin.inlines[0](AssistantConversationLog, django_admin.site)
        self.assertTrue(inline.prompt_short(self.message).endswith("..."))
        self.assertEqual(inline.token_total(self.message), 15)

    # ---- changelists ------------------------------------------------------
    def test_conversation_changelist_renders(self):
        response = self.client.get("/admin/system_intelligence/assistantconversationlog/")
        self.assertEqual(response.status_code, 200)

    def test_message_changelist_renders(self):
        response = self.client.get("/admin/system_intelligence/assistantmessagelog/")
        self.assertEqual(response.status_code, 200)

    def test_conversation_search_and_filter(self):
        url = "/admin/system_intelligence/assistantconversationlog/"
        response = self.client.get(url, {"q": "deadbeef"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Public Chat")
        filtered = self.client.get(url, {"source": AssistantConversationLog.SOURCE_AI_SEARCH})
        self.assertEqual(filtered.status_code, 200)

    def test_message_search_and_filter(self):
        url = "/admin/system_intelligence/assistantmessagelog/"
        response = self.client.get(url, {"q": "helpful"})
        self.assertEqual(response.status_code, 200)
        filtered = self.client.get(url, {"status": AssistantMessageLog.STATUS_OK})
        self.assertEqual(filtered.status_code, 200)

    def test_conversation_detail_renders_with_inline(self):
        response = self.client.get(f"/admin/system_intelligence/assistantconversationlog/{self.convo.pk}/change/")
        self.assertEqual(response.status_code, 200)

from unittest.mock import patch

from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    PublicAssistantTokenBudget,
)
from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.services.public_assistant.chat import actors
from apps.system_intelligence.tests.public_assistant.chat.test_chat_api import (
    INVOKE_PATH,
    MOCK_RESULT,
    SESSION,
    PublicAssistantChatTestBase,
)


class ConfigEndpointTests(PublicAssistantChatTestBase):
    def test_config_reflects_enabled_state(self):
        response = self.client.get(self.config_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["enabled"])
        self.assertEqual(response.data["welcome_message"], self.config.public_assistant_welcome_message)
        self.assertEqual(response.data["unavailable_message"], self.config.public_assistant_unavailable_message)
        self.assertEqual(response.data["max_message_chars"], self.config.public_assistant_max_message_chars)
        self.assertIsInstance(response.data["starter_questions"], list)
        self.assertTrue(response.data["starter_questions"])

    def test_config_reflects_disabled_state(self):
        self.config.public_assistant_enabled = False
        self.config.save()
        response = self.client.get(self.config_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["enabled"])

    def test_config_handles_non_list_starter_questions(self):
        self.config.public_assistant_starter_questions = {"bad": "shape"}
        self.config.save()
        response = self.client.get(self.config_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["starter_questions"], [])

    def test_config_issues_a_signed_visitor_identity(self):
        response = self.client.get(self.config_url)

        actor = actors.visitor_actor(response.data["visitor_token"])
        self.assertEqual(actor.kind, actors.KIND_VISITOR)
        self.assertIsNone(actor.replacement)

    def test_every_config_response_is_a_different_visitor_and_is_never_cached(self):
        first = self.client.get(self.config_url)
        second = self.client.get(self.config_url)

        self.assertNotEqual(first.data["visitor_token"], second.data["visitor_token"])
        self.assertNotEqual(
            actors.visitor_actor(first.data["visitor_token"]).key,
            actors.visitor_actor(second.data["visitor_token"]).key,
        )
        # A shared cache replaying this body would hand many people one identity.
        self.assertEqual(first["Cache-Control"], "no-store")

    def test_config_issues_no_identity_and_no_budget_rows_when_disabled(self):
        self.config.public_assistant_enabled = False
        self.config.save()

        response = self.client.get(self.config_url)

        self.assertNotIn("visitor_token", response.data)
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())


class AuditLoggingTests(PublicAssistantChatTestBase):
    def _post(self, **extra):
        payload = {"message": "What is I2G?"}
        payload.update(extra)
        return self.client.post(self.chat_url, payload, format="json")

    def test_success_logs_ok_row(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_OK)
        self.assertEqual(message.reply, MOCK_RESULT["text"])
        self.assertEqual(message.token_usage["totalTokens"], 160)
        self.assertEqual(message.conversation.source, AssistantConversationLog.SOURCE_PUBLIC_CHAT)
        self.assertEqual(message.conversation.total_tokens, 160)

    def test_unavailable_aws_logs_unavailable_row(self):
        self.aws.access_key_id = ""
        self.aws.secret_access_key = ""
        self.aws.save()
        with patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke:
            response = self._post()
        self.assertEqual(response.status_code, 200)
        mock_invoke.assert_not_called()
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_UNAVAILABLE)

    def test_budget_logs_budget_row(self):
        # The assistant's global budget is spent (these requests carry no
        # visitor value, and the legacy actor has no per-actor token limit).
        self.config.public_assistant_global_token_limit = 100
        self.config.save()
        budget.record_usage(budget.GLOBAL_BUDGET_KEYS[budget.FEATURE_ASSISTANT], 100, 86400)
        with (
            patch(INVOKE_PATH, return_value=MOCK_RESULT) as mock_invoke,
            self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 429)
        mock_invoke.assert_not_called()
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_BUDGET)

    def test_error_logs_error_row(self):
        with patch(INVOKE_PATH, side_effect=RuntimeError("boom")):
            response = self._post()
        self.assertEqual(response.status_code, 502)
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_ERROR)

    def test_session_id_groups_turns(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            self._post(session_id=SESSION)
            self._post(session_id=SESSION)
        self.assertEqual(AssistantConversationLog.objects.count(), 1)
        convo = AssistantConversationLog.objects.get()
        self.assertEqual(convo.message_count, 2)
        self.assertEqual(str(convo.session_id), SESSION)

    def test_garbage_session_id_does_not_400(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            response = self._post(session_id="not-a-uuid")
        self.assertEqual(response.status_code, 200)
        convo = AssistantConversationLog.objects.get()
        self.assertIsNone(convo.session_id)

    def test_disabled_config_branch_is_not_logged(self):
        # The widget-off branch is intentionally NOT audited (pure noise).
        self.config.public_assistant_enabled = False
        self.config.save()
        with patch(INVOKE_PATH):
            self._post()
        self.assertEqual(AssistantMessageLog.objects.count(), 0)

    def test_recorder_failure_does_not_break_response(self):
        # Force the audit write to blow up deep inside the recorder; the
        # visitor must still get their answer (the recorder swallows it).
        with (
            patch(INVOKE_PATH, return_value=MOCK_RESULT),
            patch(
                "apps.system_intelligence.services.usage_log.recorder.AssistantMessageLog.objects.create",
                side_effect=RuntimeError("audit down"),
            ),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["reply"], MOCK_RESULT["text"])
        self.assertEqual(AssistantMessageLog.objects.count(), 0)

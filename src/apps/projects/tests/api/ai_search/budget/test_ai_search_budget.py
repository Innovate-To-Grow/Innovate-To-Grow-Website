"""AI search token budgets: reservation, refusal, release and reconciliation."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.projects.models import Semester
from apps.projects.services.ai_search import (
    prepare_past_project_ai_search,
)
from apps.system_intelligence.models import (
    AssistantConversationLog,
    PublicAssistantTokenBudget,
    PublicAssistantTokenReservation,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import (
    FEATURE_ASSISTANT,
    budget,
    estimate_public_input_tokens,
    global_tokens_used,
    hash_ip,
    issue_visitor_token,
    legacy_actor,
    member_actor,
    record_usage,
    visitor_actor,
)

from ..helpers.ai_search_helpers import (
    OUTCOME_TOKENS,
    SEARCH_GLOBAL_KEY,
    SEARCH_URL,
    VIEW_SEARCH,
    Member,
    create_project,
)


# The database path is the production path (no Redis): keep it explicit here.
class _PastProjectAISearchBudgetCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.member = Member.objects.create_user(email="member@example.com", password="pw", is_active=True)
        self.other_member = Member.objects.create_user(email="other@example.com", password="pw", is_active=True)
        self.config = SystemIntelligenceConfig.objects.create(
            name="AI",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            public_assistant_ip_token_window_seconds=3600,
        )
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKIATEST",
            secret_access_key="secret",
            default_region="us-west-2",
        )
        semester = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_published=True)
        self.project = create_project(semester, project_title="Solar Sensor Irrigation Network")
        create_project(semester, project_title="Battery Health Monitor", team_number="102")
        self.outcome = {
            "project_ids": [str(self.project.id)],
            "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": OUTCOME_TOKENS},
        }
        prepared = prepare_past_project_ai_search(query="solar", limit=10, config=self.config)
        # What one search reserves before the model call: estimated prompt + output cap.
        self.reserved = prepared.estimated_input_tokens + prepared.max_tokens
        self.member_key = member_actor(self.member.pk).key
        self.other_key = member_actor(self.other_member.pk).key

    def configure(self, **fields):
        for name, value in fields.items():
            setattr(self.config, name, value)
        self.config.save()

    def search(self, member=None, *, query="solar", ip="169.236.10.10"):
        self.client.force_authenticate(user=member or self.member)
        return self.client.post(SEARCH_URL, {"query": query}, format="json", REMOTE_ADDR=ip)

    def _chat_reserved(self):
        """What one public-assistant turn reserves before its model call."""
        return (
            estimate_public_input_tokens(message="hi", history=[], config=self.config, context="ctx")
            + self.config.public_assistant_max_response_tokens
        )

    def _anonymous_chat(self, *, minted_identities):
        """Chat turns the way an anonymous script sends them: a freshly minted identity each time."""
        self.client.force_authenticate(user=None)
        statuses = []
        with (
            patch("apps.system_intelligence.views.chat_turn.build_public_context", return_value="ctx"),
            patch(
                "apps.system_intelligence.views.chat_turn.answer_public_question",
                return_value={"text": "hello", "usage": {"totalTokens": 5}},
            ) as mock_answer,
        ):
            for _ in range(minted_identities):
                token = self.client.get("/assistant/config/").data["visitor_token"]
                response = self.client.post(
                    "/assistant/chat/",
                    {"message": "hi", "visitor_token": token},
                    format="json",
                    REMOTE_ADDR="198.51.100.7",
                )
                statuses.append(response.status_code)
        return statuses, mock_answer.call_count


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class PastProjectAISearchBudgetTests(_PastProjectAISearchBudgetCase):
    """Token budgets: per MEMBER (never per IP) plus AI search's own global spend ceiling."""

    def test_search_charges_the_member_and_the_global_budget_not_the_ip(self):
        with patch(VIEW_SEARCH, return_value=self.outcome):
            response = self.search(ip="169.236.10.10")

        self.assertEqual(response.status_code, 200)
        used = dict(PublicAssistantTokenBudget.objects.values_list("pk", "tokens_used"))
        # The member's row and AI search's global row -- not the assistant's.
        self.assertEqual(used, {self.member_key: OUTCOME_TOKENS, SEARCH_GLOBAL_KEY: OUTCOME_TOKENS})
        self.assertEqual(global_tokens_used(FEATURE_ASSISTANT), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())
        # The hashed IP is still recorded for audit, but keys no budget.
        self.assertEqual(AssistantConversationLog.objects.get().ip_hash, hash_ip("169.236.10.10"))

    def test_budgets_are_per_member_behind_one_campus_ip(self):
        self.configure(public_assistant_ip_token_limit=self.reserved)
        record_usage(self.member_key, self.reserved, 3600)

        with patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search:
            exhausted = self.search(self.member)
            other = self.search(self.other_member)

        self.assertEqual(exhausted.status_code, 429)
        self.assertEqual(exhausted.data["code"], "budget_exceeded")
        self.assertEqual(other.status_code, 200)
        self.assertTrue(other.data["available"])
        mocked_search.assert_called_once()
        self.assertEqual(budget.tokens_used(self.other_key), OUTCOME_TOKENS)

    def test_exhausted_assistant_buckets_do_not_block_a_member_search(self):
        self.configure(public_assistant_ip_token_limit=self.reserved)
        visitor_key = visitor_actor(issue_visitor_token()).key
        for key in (visitor_key, legacy_actor().key, hash_ip("169.236.10.10")):
            record_usage(key, self.reserved, 3600)

        with patch(VIEW_SEARCH, return_value=self.outcome):
            response = self.search()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])

    def test_exhausted_member_does_not_block_the_anonymous_assistant(self):
        self.configure(public_assistant_ip_token_limit=5000, public_assistant_enabled=True)
        record_usage(self.member_key, 5000, 3600)
        with patch(VIEW_SEARCH, return_value=self.outcome) as mocked_search:
            self.assertEqual(self.search().status_code, 429)
        mocked_search.assert_not_called()
        self.client.force_authenticate(user=None)

        with (
            patch("apps.system_intelligence.views.chat_turn.build_public_context", return_value="ctx"),
            patch(
                "apps.system_intelligence.views.chat_turn.answer_public_question",
                return_value={"text": "hello", "usage": {"totalTokens": 5}},
            ),
        ):
            token = self.client.get("/assistant/config/").data["visitor_token"]
            response = self.client.post(
                "/assistant/chat/",
                {"message": "hi", "visitor_token": token},
                format="json",
                REMOTE_ADDR="169.236.10.10",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])

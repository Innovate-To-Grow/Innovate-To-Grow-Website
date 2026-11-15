"""API-level tests: the public assistant's limits are per actor, never per IP.

Essentially every user of this site shares ONE campus public address, so these
tests send whole classrooms through a single IP and expect each visitor to be
served, while the global budget still bounds what the site can spend.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import (
    PublicAssistantTokenBudget,
    PublicAssistantTokenReservation,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import budget, estimate_public_input_tokens
from apps.system_intelligence.services.public_assistant.chat import actors

Member = get_user_model()

ACTUAL_TOKENS = 160
MOCK_RESULT = {
    "text": "Innovate to Grow connects student teams with industry partners.",
    "usage": {"inputTokens": 120, "outputTokens": 40, "totalTokens": ACTUAL_TOKENS},
}
INVOKE_PATH = "apps.system_intelligence.views.chat_turn.answer_public_question"
CONTEXT_PATH = "apps.system_intelligence.views.chat_turn.build_public_context"
BUDGET_LOGGER = "apps.system_intelligence.services.public_assistant.budget"
BUDGET_MESSAGE = "The assistant has reached its usage limit for now. Please try again later."
CAMPUS_IP = "169.236.10.10"
MESSAGE = "hi"
DAY = 24 * 60 * 60
ASSISTANT = budget.FEATURE_ASSISTANT
AI_SEARCH = budget.FEATURE_AI_SEARCH
ASSISTANT_GLOBAL_KEY = budget.GLOBAL_BUDGET_KEYS[ASSISTANT]


# The database path is the production path (no Redis): keep it explicit here.
@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class ActorLimitsTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.chat_url = reverse("system_intelligence:public-assistant-chat")
        self.config_url = reverse("system_intelligence:public-assistant-config")
        self.config = SystemIntelligenceConfig.objects.create(
            name="Test",
            is_active=True,
            public_assistant_enabled=True,
            public_assistant_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            public_assistant_system_prompt="Be brief.",
            public_assistant_max_response_tokens=100,
        )
        AWSCredentialConfig.objects.create(
            name="Test AWS",
            is_active=True,
            access_key_id="AKIATESTKEY",
            secret_access_key="secret",
            default_region="us-west-2",
        )
        context = patch(CONTEXT_PATH, return_value="ctx")
        context.start()
        self.addCleanup(context.stop)
        invoke = patch(INVOKE_PATH, return_value=MOCK_RESULT)
        self.invoke = invoke.start()
        self.addCleanup(invoke.stop)
        # What one turn reserves before the model call: estimated input + output cap.
        self.reserved = (
            estimate_public_input_tokens(message=MESSAGE, history=[], config=self.config, context="ctx")
            + self.config.public_assistant_max_response_tokens
        )

    def configure(self, **fields):
        for name, value in fields.items():
            setattr(self.config, name, value)
        self.config.save()

    def new_visitor(self) -> str:
        """What a browser does on page load: fetch config, keep the visitor value."""
        return self.client.get(self.config_url, REMOTE_ADDR=CAMPUS_IP).data["visitor_token"]

    def ask(self, visitor=None, *, ip=CAMPUS_IP, **extra):
        payload = {"message": MESSAGE}
        if visitor is not None:
            payload["visitor_token"] = visitor
        return self.client.post(self.chat_url, payload, format="json", REMOTE_ADDR=ip, **extra)

    def used(self, visitor: str) -> int:
        return budget.tokens_used(actors.visitor_actor(visitor).key)

    def actor_rows(self):
        return PublicAssistantTokenBudget.objects.exclude(pk__in=list(budget.GLOBAL_BUDGET_KEYS.values()))


class _CampusSharedIpCase(ActorLimitsTestBase):
    def setUp(self):
        super().setUp()
        # One actor can afford exactly two turns in the window. A bucket shared
        # by the campus (the old per-IP key) would therefore serve 2 people.
        self.configure(public_assistant_ip_token_limit=self.reserved + ACTUAL_TOKENS)


class CampusSharedIpTests(_CampusSharedIpCase):
    def test_forty_visitors_behind_one_campus_ip_each_get_an_answer(self):
        visitors = [self.new_visitor() for _ in range(40)]

        statuses = [self.ask(visitor).status_code for visitor in visitors]

        self.assertEqual(statuses, [200] * 40)
        self.assertEqual(self.invoke.call_count, 40)
        self.assertEqual(self.actor_rows().count(), 40)
        self.assertEqual({self.used(visitor) for visitor in visitors}, {ACTUAL_TOKENS})
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 40 * ACTUAL_TOKENS)
        self.assertEqual(budget.tokens_used(budget.hash_ip(CAMPUS_IP)), 0)

    def test_one_visitor_exhausting_their_budget_does_not_affect_another(self):
        heavy, other = self.new_visitor(), self.new_visitor()

        heavy_statuses = [self.ask(heavy).status_code for _ in range(3)]
        other_response = self.ask(other)
        heavy_again = self.ask(heavy)

        self.assertEqual(heavy_statuses, [200, 200, 429])
        self.assertEqual(other_response.status_code, 200)
        self.assertTrue(other_response.data["available"])
        self.assertEqual(heavy_again.status_code, 429)
        self.assertEqual(heavy_again.data["code"], "budget_exceeded")
        self.assertEqual(heavy_again.data["detail"], BUDGET_MESSAGE)
        self.assertEqual(self.used(heavy), 2 * ACTUAL_TOKENS)
        self.assertEqual(self.used(other), ACTUAL_TOKENS)
        self.assertEqual(self.invoke.call_count, 3)

    def test_sixty_requests_without_an_identity_from_sixty_ips_are_all_answered(self):
        # Old cached bundles and token-less callers are ONE actor standing for
        # many people. A single visitor's allowance (two turns here) would be
        # gone after the second of them, so the legacy actor is exempt from the
        # per-actor token limit: the assistant's global budget and the legacy
        # request throttle (60/minute) are what bound it.
        statuses = [self.ask(ip=f"203.0.113.{index}").status_code for index in range(1, 61)]

        self.assertEqual(statuses, [200] * 60)
        self.assertEqual(self.invoke.call_count, 60)
        # Still ONE actor row, whatever the address, and it is still accounted.
        self.assertEqual(list(self.actor_rows().values_list("pk", flat=True)), [actors.legacy_actor().key])
        self.assertEqual(budget.tokens_used(actors.legacy_actor().key), 60 * ACTUAL_TOKENS)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 60 * ACTUAL_TOKENS)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_the_global_budget_still_stops_requests_without_an_identity(self):
        # Room for exactly three turns site-wide.
        self.configure(public_assistant_global_token_limit=self.reserved + 2 * ACTUAL_TOKENS)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            responses = [self.ask(ip=f"203.0.113.{index}") for index in range(1, 7)]

        self.assertEqual([response.status_code for response in responses], [200, 200, 200, 429, 429, 429])
        for refused in responses[3:]:
            self.assertEqual(refused.data["code"], "budget_exceeded")
            self.assertEqual(refused.data["detail"], BUDGET_MESSAGE)
        self.assertEqual(self.invoke.call_count, 3)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 3 * ACTUAL_TOKENS)
        self.assertEqual(budget.tokens_used(actors.legacy_actor().key), 3 * ACTUAL_TOKENS)
        self.assertIn("global token budget exhausted for Public assistant", logs.output[0])

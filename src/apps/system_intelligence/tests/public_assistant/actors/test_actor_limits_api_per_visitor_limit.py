import time
from unittest.mock import patch

from django.core import signing
from django.test import override_settings

from apps.system_intelligence.models import (
    AssistantConversationLog,
    PublicAssistantTokenBudget,
)
from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.services.public_assistant.chat import actors
from apps.system_intelligence.tests.public_assistant.actors.test_actor_limits_api import (
    ACTUAL_TOKENS,
    ASSISTANT,
    DAY,
    _CampusSharedIpCase,
)


class CampusSharedIpTests(_CampusSharedIpCase):
    def test_the_per_visitor_limit_still_binds_everyone_with_an_identity(self):
        # Heavy use of the legacy actor neither lifts nor uses up a visitor's own allowance.
        self.assertEqual([self.ask().status_code for _ in range(5)], [200] * 5)
        visitor = self.new_visitor()

        statuses = [self.ask(visitor).status_code for _ in range(3)]

        self.assertEqual(statuses, [200, 200, 429])
        self.assertEqual(self.ask().status_code, 200)

    def test_self_made_or_expired_values_all_land_in_the_one_legacy_actor(self):
        genuine = self.new_visitor()
        with override_settings(SECRET_KEY="an-attacker-chosen-signing-key"):
            self_signed = [actors.issue_visitor_token() for _ in range(3)]
        tampered = genuine[:-2] + ("AA" if not genuine.endswith("AA") else "BB")
        attempts = [
            "made-up-value",
            signing.dumps({"v": "e" * 32}, salt="some.other.feature"),
            tampered,
            *self_signed,
        ]
        responses = [self.ask(attempt) for attempt in attempts]
        with patch("django.core.signing.time.time", return_value=time.time() + 31 * DAY):
            responses.append(self.ask(genuine))

        # Never rejected, and never a bucket of their own: inventing values
        # buys nothing, because every one of them is the single legacy actor
        # (bounded by its request throttle and the assistant's global budget).
        self.assertEqual({response.status_code for response in responses}, {200})
        self.assertEqual(list(self.actor_rows().values_list("pk", flat=True)), [actors.legacy_actor().key])
        self.assertEqual(budget.tokens_used(actors.legacy_actor().key), len(responses) * ACTUAL_TOKENS)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), len(responses) * ACTUAL_TOKENS)
        for response in responses:
            self.assertEqual(actors.visitor_actor(response.data["visitor_token"]).kind, actors.KIND_VISITOR)
        # ... while the genuine, unexpired value has a budget row of its own.
        self.assertEqual(self.ask(genuine).status_code, 200)
        self.assertEqual(self.actor_rows().count(), 2)
        self.assertEqual(self.used(genuine), ACTUAL_TOKENS)

    def test_hashed_ip_is_still_recorded_for_audit(self):
        self.ask(self.new_visitor(), ip="203.0.113.5")

        conversation = AssistantConversationLog.objects.get()
        self.assertEqual(conversation.ip_hash, budget.hash_ip("203.0.113.5"))
        self.assertFalse(PublicAssistantTokenBudget.objects.filter(pk=conversation.ip_hash).exists())

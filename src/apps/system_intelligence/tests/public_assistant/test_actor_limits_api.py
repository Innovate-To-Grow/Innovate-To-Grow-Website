"""API-level tests: the public assistant's limits are per actor, never per IP.

Essentially every user of this site shares ONE campus public address, so these
tests send whole classrooms through a single IP and expect each visitor to be
served, while the global budget still bounds what the site can spend.
"""

import time
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    PublicAssistantTokenBudget,
    PublicAssistantTokenReservation,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import actors, budget, estimate_public_input_tokens

Member = get_user_model()

ACTUAL_TOKENS = 160
MOCK_RESULT = {
    "text": "Innovate to Grow connects student teams with industry partners.",
    "usage": {"inputTokens": 120, "outputTokens": 40, "totalTokens": ACTUAL_TOKENS},
}
INVOKE_PATH = "apps.system_intelligence.views.public_assistant.answer_public_question"
CONTEXT_PATH = "apps.system_intelligence.views.public_assistant.build_public_context"
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


class CampusSharedIpTests(ActorLimitsTestBase):
    def setUp(self):
        super().setUp()
        # One actor can afford exactly two turns in the window. A bucket shared
        # by the campus (the old per-IP key) would therefore serve 2 people.
        self.configure(public_assistant_ip_token_limit=self.reserved + ACTUAL_TOKENS)

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


class GlobalBudgetTests(ActorLimitsTestBase):
    def test_global_budget_stops_everyone_with_the_budget_message(self):
        # Fits exactly two turns for the whole site; per-actor limits are far away.
        self.configure(public_assistant_global_token_limit=self.reserved + ACTUAL_TOKENS)
        first, second, third = self.new_visitor(), self.new_visitor(), self.new_visitor()
        self.assertEqual([self.ask(first).status_code, self.ask(second).status_code], [200, 200])

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            refused = [self.ask(third), self.ask(first), self.ask()]

        for response in refused:
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.data["code"], "budget_exceeded")
            self.assertEqual(response.data["detail"], BUDGET_MESSAGE)
        self.assertEqual(self.invoke.call_count, 2)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 2 * ACTUAL_TOKENS)
        # A refusal charges nobody: no row for the third visitor or the legacy bucket.
        self.assertEqual(self.actor_rows().count(), 2)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(
            AssistantMessageLog.objects.filter(status=AssistantMessageLog.STATUS_BUDGET).count(),
            3,
        )

    def test_reservation_is_held_on_both_budgets_during_the_model_call(self):
        visitor = self.new_visitor()
        seen = {}

        def invoke(**_kwargs):
            seen["actor"] = self.used(visitor)
            seen["global"] = budget.global_tokens_used(ASSISTANT)
            seen["reservations"] = PublicAssistantTokenReservation.objects.count()
            return MOCK_RESULT

        self.invoke.side_effect = invoke

        self.assertEqual(self.ask(visitor).status_code, 200)

        self.assertEqual(seen, {"actor": self.reserved, "global": self.reserved, "reservations": 2})

    def test_success_reconciles_both_budgets_to_actual_usage(self):
        visitor = self.new_visitor()

        self.ask(visitor)

        self.assertEqual(self.used(visitor), ACTUAL_TOKENS)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), ACTUAL_TOKENS)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_provider_error_releases_both_budgets(self):
        self.configure(public_assistant_global_token_limit=self.reserved)
        visitor = self.new_visitor()
        self.invoke.side_effect = RuntimeError("bedrock down")

        failures = [self.ask(visitor).status_code for _ in range(3)]

        # Nothing leaked: three failed calls in a row still fit a budget of one.
        self.assertEqual(failures, [502, 502, 502])
        self.assertEqual(self.used(visitor), 0)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

        self.invoke.side_effect = None
        self.assertEqual(self.ask(visitor).status_code, 200)

    def test_zero_global_limit_switches_the_model_calls_off(self):
        self.configure(public_assistant_global_token_limit=0)

        responses = [self.ask(self.new_visitor()), self.ask()]

        for response in responses:
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.data["code"], "budget_exceeded")
            self.assertEqual(response.data["detail"], BUDGET_MESSAGE)
        self.invoke.assert_not_called()
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_raising_the_global_limit_restores_service_immediately(self):
        self.configure(public_assistant_global_token_limit=self.reserved)
        visitor = self.new_visitor()
        self.assertEqual(self.ask(visitor).status_code, 200)
        with self.assertLogs(BUDGET_LOGGER, level="WARNING"):
            self.assertEqual(self.ask(visitor).status_code, 429)

        self.configure(public_assistant_global_token_limit=10 * self.reserved)

        self.assertEqual(self.ask(visitor).status_code, 200)

    def test_chat_is_charged_to_the_assistants_global_row_only(self):
        self.ask(self.new_visitor())

        self.assertEqual(budget.global_tokens_used(ASSISTANT), ACTUAL_TOKENS)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 0)
        self.assertFalse(
            PublicAssistantTokenBudget.objects.filter(pk=budget.GLOBAL_BUDGET_KEYS[AI_SEARCH]).exists(),
        )

    def test_spent_ai_search_budget_does_not_pause_the_assistant(self):
        self.configure(public_assistant_global_token_limit=self.reserved)
        budget.record_usage(budget.GLOBAL_BUDGET_KEYS[AI_SEARCH], self.reserved, DAY)

        with self.assertNoLogs(BUDGET_LOGGER, level="WARNING"):
            response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(budget.global_tokens_used(ASSISTANT), ACTUAL_TOKENS)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), self.reserved)

    def test_default_global_limit_is_two_million_tokens(self):
        self.assertEqual(SystemIntelligenceConfig().public_assistant_global_token_limit, 2_000_000)
        self.assertEqual(self.config.public_assistant_global_token_limit, 2_000_000)

    def test_budget_backend_failure_is_a_503_never_a_500(self):
        with patch.object(budget, "_locked_database_budget", side_effect=RuntimeError("db down")):
            response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "budget_unavailable")
        self.invoke.assert_not_called()


class FailurePathTests(ActorLimitsTestBase):
    """Infrastructure hiccups around the budget never become a 500 or a leak."""

    def test_context_failure_is_a_503_and_reserves_nothing(self):
        with patch(CONTEXT_PATH, side_effect=RuntimeError("cache down")):
            response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "budget_unavailable")
        self.invoke.assert_not_called()
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_reconcile_failure_does_not_break_the_answer(self):
        with patch(
            "apps.system_intelligence.views.public_assistant.reconcile_budget",
            side_effect=budget.BudgetBackendUnavailable("db blip"),
        ):
            response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reply"], MOCK_RESULT["text"])

    def test_unparsable_provider_usage_is_answered_and_settled_at_the_reservation(self):
        # Not a number: no 500, and neither reservation is left dangling.
        visitor = self.new_visitor()
        self.invoke.return_value = {"text": "An answer.", "usage": {"totalTokens": "n/a"}}

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            response = self.ask(visitor)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["reply"], "An answer.")
        self.assertIn("Unparsable provider token usage", logs.output[0])
        self.assertEqual(self.used(visitor), self.reserved)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), self.reserved)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_release_failure_after_a_provider_error_still_answers_502(self):
        self.invoke.side_effect = RuntimeError("bedrock down")
        with patch(
            "apps.system_intelligence.views.public_assistant.release_budget",
            side_effect=budget.BudgetBackendUnavailable("db blip"),
        ):
            response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "assistant_error")

    def test_input_too_large_is_rejected_before_any_reservation(self):
        self.configure(public_assistant_max_estimated_input_tokens=5)

        response = self.ask()

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.data["code"], "input_too_large")
        self.assertEqual(actors.visitor_actor(response.data["visitor_token"]).kind, actors.KIND_VISITOR)
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())


class VisitorIdentityHandoverTests(ActorLimitsTestBase):
    def test_request_without_identity_is_answered_and_handed_one_to_store(self):
        response = self.ask()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        handed = response.data["visitor_token"]
        self.assertEqual(actors.visitor_actor(handed).kind, actors.KIND_VISITOR)

        follow_up = self.ask(handed)

        self.assertEqual(follow_up.status_code, 200)
        self.assertNotIn("visitor_token", follow_up.data)
        self.assertEqual(self.used(handed), ACTUAL_TOKENS)
        self.assertEqual(budget.tokens_used(actors.legacy_actor().key), ACTUAL_TOKENS)

    def test_valid_identity_gets_no_replacement(self):
        response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("visitor_token", response.data)

    def test_budget_refusal_without_an_identity_still_hands_one_over(self):
        # Only the global budget can refuse the legacy actor.
        self.configure(public_assistant_global_token_limit=self.reserved)
        budget.record_usage(ASSISTANT_GLOBAL_KEY, 1, DAY)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING"):
            refused = self.ask("an-expired-or-unknown-value")

        self.assertEqual(refused.status_code, 429)
        self.assertEqual(refused.data["code"], "budget_exceeded")
        handed = refused.data["visitor_token"]
        self.assertEqual(actors.visitor_actor(handed).kind, actors.KIND_VISITOR)
        # Once the budget has room again, that identity has a bucket of its own.
        self.configure(public_assistant_global_token_limit=10 * self.reserved)
        self.assertEqual(self.ask(handed).status_code, 200)
        self.assertEqual(self.used(handed), ACTUAL_TOKENS)

    def test_ageing_identity_is_renewed_without_changing_its_budget(self):
        visitor = self.new_visitor()
        self.ask(visitor)

        with patch("django.core.signing.time.time", return_value=time.time() + 16 * DAY):
            response = self.ask(visitor)
            renewed = response.data["visitor_token"]
            self.assertEqual(actors.visitor_actor(renewed).key, actors.visitor_actor(visitor).key)
            self.assertIsNone(actors.visitor_actor(renewed).replacement)

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(renewed, visitor)
        self.assertEqual(self.used(visitor), 2 * ACTUAL_TOKENS)
        self.assertEqual(self.actor_rows().count(), 1)

    def test_unusable_identity_values_never_reject_the_request(self):
        for value in ({"nested": "object"}, ["list"], 12345, 1.5, True, None, "", "x" * 5000):
            with self.subTest(value=value):
                response = self.client.post(
                    self.chat_url,
                    {"message": MESSAGE, "visitor_token": value},
                    format="json",
                    REMOTE_ADDR=CAMPUS_IP,
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data["available"])
        self.assertEqual(list(self.actor_rows().values_list("pk", flat=True)), [actors.legacy_actor().key])

    def test_malformed_bodies_are_a_400_not_a_500(self):
        not_an_object = self.client.post(self.chat_url, ["hi"], format="json")
        not_json = self.client.post(self.chat_url, "{not json", content_type="application/json")

        self.assertEqual(not_an_object.status_code, 400)
        self.assertEqual(not_json.status_code, 400)
        self.invoke.assert_not_called()

    def test_unavailable_answer_also_hands_over_an_identity(self):
        AWSCredentialConfig.objects.update(access_key_id="", secret_access_key="")

        response = self.ask()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        self.assertEqual(actors.visitor_actor(response.data["visitor_token"]).kind, actors.KIND_VISITOR)

    def test_authenticated_member_is_keyed_on_the_member(self):
        member = Member.objects.create_user(email="member@example.com", password="pw", is_active=True)
        self.client.force_authenticate(user=member)

        response = self.ask(self.new_visitor())

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("visitor_token", response.data)
        self.assertEqual(
            list(self.actor_rows().values_list("pk", flat=True)),
            [actors.member_actor(member.pk).key],
        )


class RequestRateTests(ActorLimitsTestBase):
    """PublicAssistantActorThrottle: 6/minute per actor, 60/minute for the legacy bucket."""

    def test_configured_rates(self):
        from apps.system_intelligence.views import PublicAssistantActorThrottle

        self.assertEqual(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["public_assistant"], "6/minute")
        self.assertEqual(PublicAssistantActorThrottle.legacy_default_rate, "60/minute")

    def test_a_visitor_gets_six_requests_a_minute(self):
        visitor = self.new_visitor()

        statuses = [self.ask(visitor).status_code for _ in range(7)]

        self.assertEqual(statuses, [200] * 6 + [429])
        self.assertEqual(self.invoke.call_count, 6)

    def test_throttled_response_is_the_framework_one_and_spends_nothing(self):
        visitor = self.new_visitor()
        for _ in range(6):
            self.ask(visitor)

        throttled = self.ask(visitor)

        self.assertEqual(throttled.status_code, 429)
        self.assertIn("throttled", throttled.data["detail"])
        self.assertNotIn("code", throttled.data)
        # A current identity needs no replacement.
        self.assertNotIn("visitor_token", throttled.data)
        self.assertGreater(int(throttled["Retry-After"]), 0)
        self.assertEqual(self.used(visitor), 6 * ACTUAL_TOKENS)

    def test_throttled_legacy_caller_is_still_handed_an_identity_to_leave_the_bucket(self):
        # A saturated legacy bucket answers nothing but 429s. A browser whose
        # value lapsed must be able to get out of it from that 429 alone.
        rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "public_assistant_legacy": "1/minute"}
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}):
            self.assertEqual(self.ask("someone-else-without-a-value").status_code, 200)

            throttled = self.ask("a-lapsed-value")

            self.assertEqual(throttled.status_code, 429)
            self.assertIn("throttled", throttled.data["detail"])
            self.assertGreater(int(throttled["Retry-After"]), 0)
            handed = throttled.data["visitor_token"]
            self.assertEqual(actors.visitor_actor(handed).kind, actors.KIND_VISITOR)
            self.assertEqual(self.ask().status_code, 429)
            self.assertEqual(self.ask(handed).status_code, 200)
        self.assertEqual(self.invoke.call_count, 2)

    def test_one_throttled_visitor_does_not_throttle_the_rest_of_the_campus(self):
        noisy = self.new_visitor()
        for _ in range(7):
            self.ask(noisy)
        classroom = [self.new_visitor() for _ in range(25)]

        statuses = [self.ask(visitor).status_code for visitor in classroom]

        # The old per-IP throttle answered the 21st campus request with 429.
        self.assertEqual(statuses, [200] * 25)
        self.assertEqual(self.ask(noisy).status_code, 429)

    def test_rate_limit_follows_the_visitor_not_the_ip(self):
        visitor = self.new_visitor()

        statuses = [
            self.ask(visitor, ip=f"198.51.100.{index}", HTTP_X_FORWARDED_FOR=f"10.9.8.{index}").status_code
            for index in range(1, 8)
        ]

        self.assertEqual(statuses, [200] * 6 + [429])

    def test_legacy_bucket_gets_sixty_requests_a_minute_in_total(self):
        statuses = [self.ask(ip=f"203.0.113.{index % 250}").status_code for index in range(61)]

        self.assertEqual(statuses, [200] * 60 + [429])
        # Real visitors are not in that bucket.
        self.assertEqual(self.ask(self.new_visitor()).status_code, 200)

    def test_self_made_values_share_the_legacy_rate_bucket(self):
        rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "public_assistant_legacy": "3/minute"}
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}):
            statuses = [self.ask(f"made-up-{index}").status_code for index in range(4)]
            real_visitor = self.ask(self.new_visitor()).status_code

        self.assertEqual(statuses, [200, 200, 200, 429])
        self.assertEqual(real_visitor, 200)

    def test_visitor_rate_is_read_live_from_settings(self):
        rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "public_assistant": "2/minute"}
        visitor = self.new_visitor()
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}):
            statuses = [self.ask(visitor).status_code for _ in range(3)]

        self.assertEqual(statuses, [200, 200, 429])

    def test_members_are_throttled_per_member(self):
        first = Member.objects.create_user(email="first@example.com", password="pw", is_active=True)
        second = Member.objects.create_user(email="second@example.com", password="pw", is_active=True)

        self.client.force_authenticate(user=first)
        first_statuses = [self.ask().status_code for _ in range(7)]
        self.client.force_authenticate(user=second)
        second_status = self.ask().status_code

        self.assertEqual(first_statuses, [200] * 6 + [429])
        self.assertEqual(second_status, 200)

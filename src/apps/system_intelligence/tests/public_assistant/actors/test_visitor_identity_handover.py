import time
from unittest.mock import patch

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.services.public_assistant.chat import actors
from apps.system_intelligence.tests.public_assistant.actors.test_actor_limits_api import (
    ACTUAL_TOKENS,
    ASSISTANT_GLOBAL_KEY,
    BUDGET_LOGGER,
    CAMPUS_IP,
    DAY,
    MESSAGE,
    ActorLimitsTestBase,
    Member,
)


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

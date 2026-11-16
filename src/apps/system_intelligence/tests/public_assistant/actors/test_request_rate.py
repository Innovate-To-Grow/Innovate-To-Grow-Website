from django.conf import settings

from apps.core.tests.request_limits.helpers import view_limit
from apps.system_intelligence.services.public_assistant.chat import actors
from apps.system_intelligence.tests.public_assistant.actors.test_actor_limits_api import (
    ACTUAL_TOKENS,
    ActorLimitsTestBase,
    Member,
)


class RequestRateTests(ActorLimitsTestBase):
    """PublicAssistantActorThrottle: 6/minute per actor, 60/minute for the legacy bucket."""

    def test_configured_rates(self):
        from apps.system_intelligence.views import PublicAssistantActorThrottle

        scopes = settings.REQUEST_RATE_LIMITS["scopes"]
        self.assertEqual(PublicAssistantActorThrottle.policy_scope, "view-assistant-chat")
        self.assertEqual(PublicAssistantActorThrottle.legacy_policy_scope, "view-assistant-legacy")
        self.assertEqual(
            (scopes["view-assistant-chat"]["requests"], scopes["view-assistant-chat"]["period_seconds"]), (6, 60)
        )
        self.assertEqual(
            (scopes["view-assistant-legacy"]["requests"], scopes["view-assistant-legacy"]["period_seconds"]), (60, 60)
        )

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
        with view_limit(**{"view-assistant-legacy": (1, 60)}):
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
        with view_limit(**{"view-assistant-legacy": (3, 60)}):
            statuses = [self.ask(f"made-up-{index}").status_code for index in range(4)]
            real_visitor = self.ask(self.new_visitor()).status_code

        self.assertEqual(statuses, [200, 200, 200, 429])
        self.assertEqual(real_visitor, 200)

    def test_visitor_rate_is_read_live_from_settings(self):
        visitor = self.new_visitor()
        with view_limit(**{"view-assistant-chat": (2, 60)}):
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

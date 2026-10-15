"""A stale stored session must not break the public assistant endpoints.

The SPA sends whatever access token local storage holds with every request, and DRF authenticates before it
checks permissions. The config read never looks at the caller, so it runs no authentication. The chat endpoint keys
its throttle and token budgets on an actor resolved from ``request.user`` (the member behind a valid token, else the
visitor in the body), so it honours a valid token and treats a bad one as the visitor that sent it.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.authn.tests.stale_bearer import (
    assert_stale_bearer_reads_as_anonymous,
    stale_bearer_headers,
    valid_bearer_header,
)
from apps.system_intelligence.services.public_assistant import actors
from apps.system_intelligence.tests.public_assistant.test_actor_limits_api import ActorLimitsTestBase

Member = get_user_model()


def visitor_rate(rate):
    rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "public_assistant": rate}
    return override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates})


class PublicAssistantStaleBearerTests(ActorLimitsTestBase):
    def test_config_stale_bearer_reads_as_anonymous(self):
        assert_stale_bearer_reads_as_anonymous(
            self,
            lambda **extra: self.client.get(self.config_url, **extra),
            # Every config read mints a fresh visitor value.
            project=lambda response: {k: v for k, v in response.data.items() if k != "visitor_token"},
        )

    def test_chat_stale_bearer_reads_as_anonymous(self):
        assert_stale_bearer_reads_as_anonymous(
            self,
            lambda **extra: self.ask(self.new_visitor(), **extra),
            project=lambda response: response.data["available"],
        )

    def test_chat_stale_bearer_stays_the_visitor_that_sent_it(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label), visitor_rate("2/minute"):
                visitor = self.new_visitor()

                statuses = [self.ask(visitor, HTTP_AUTHORIZATION=header).status_code for _ in range(3)]

                self.assertEqual(statuses, [200, 200, 429])
                self.assertIn(actors.visitor_actor(visitor).key, self.actor_rows().values_list("pk", flat=True))

    def test_chat_valid_bearer_is_the_member_not_the_visitor(self):
        member = Member.objects.create_user(password="testpass123", is_active=True)
        header = valid_bearer_header(member)
        with visitor_rate("2/minute"):
            visitor = self.new_visitor()
            exhausted = [self.ask(visitor).status_code for _ in range(3)]

            as_member = self.ask(visitor, HTTP_AUTHORIZATION=header)
            as_stale = self.ask(visitor, HTTP_AUTHORIZATION=stale_bearer_headers()["garbage token"])

        self.assertEqual(exhausted, [200, 200, 429])
        self.assertEqual(as_member.status_code, 200)  # the member's own bucket, not the exhausted visitor's
        self.assertNotIn("visitor_token", as_member.data)
        self.assertIn(actors.member_actor(member.pk).key, self.actor_rows().values_list("pk", flat=True))
        self.assertEqual(as_stale.status_code, 429)  # a stale token is still the exhausted visitor

"""A stale stored session must not break the public assistant endpoints.

The SPA sends whatever access token local storage holds with every request, and DRF authenticates before it
checks permissions. The config read never looks at the caller, so it runs no authentication. The chat endpoint is
throttled by ``AnonRateThrottle``, which reads ``request.user`` to skip signed-in members, so it honours a valid
token and treats a bad one as an anonymous, throttled caller.
"""

from unittest.mock import patch

from django.core.cache import cache

from apps.authn.models import Member
from apps.authn.tests.stale_bearer import (
    assert_stale_bearer_reads_as_anonymous,
    stale_bearer_headers,
    valid_bearer_header,
)
from apps.system_intelligence.tests.public_assistant.test_chat_api import (
    INVOKE_PATH,
    MOCK_RESULT,
    PublicAssistantChatTestBase,
)
from apps.system_intelligence.views.public_assistant import PublicAssistantThrottle


class PublicAssistantStaleBearerTests(PublicAssistantChatTestBase):
    def test_config_stale_bearer_reads_as_anonymous(self):
        assert_stale_bearer_reads_as_anonymous(self, lambda **extra: self.client.get(self.config_url, **extra))

    def test_chat_stale_bearer_reads_as_anonymous(self):
        with patch(INVOKE_PATH, return_value=MOCK_RESULT):
            assert_stale_bearer_reads_as_anonymous(
                self,
                lambda **extra: self.client.post(self.chat_url, {"message": "hi"}, format="json", **extra),
                # A fresh conversation id is minted for every turn.
                project=lambda response: response.data["available"],
            )

    def test_chat_stale_bearer_is_throttled_like_an_anonymous_caller(self):
        with (
            patch(INVOKE_PATH, return_value=MOCK_RESULT),
            patch.object(PublicAssistantThrottle, "THROTTLE_RATES", {"public_assistant": "2/minute"}),
        ):
            for label, header in stale_bearer_headers().items():
                with self.subTest(stale=label):
                    cache.clear()  # the subtests share one IP, so give each a fresh throttle bucket
                    statuses = [
                        self.client.post(
                            self.chat_url, {"message": "hi"}, format="json", HTTP_AUTHORIZATION=header
                        ).status_code
                        for _ in range(3)
                    ]

                    self.assertEqual(statuses, [200, 200, 429])

    def test_chat_valid_bearer_is_not_throttled_as_anonymous(self):
        member = Member.objects.create_user(password="testpass123", is_active=True)
        with (
            patch(INVOKE_PATH, return_value=MOCK_RESULT),
            patch.object(PublicAssistantThrottle, "THROTTLE_RATES", {"public_assistant": "2/minute"}),
        ):
            statuses = [
                self.client.post(
                    self.chat_url, {"message": "hi"}, format="json", HTTP_AUTHORIZATION=valid_bearer_header(member)
                ).status_code
                for _ in range(3)
            ]

        self.assertEqual(statuses, [200, 200, 200])

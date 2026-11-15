from apps.core.services.delivery_rates import Reason, SignalKind
from apps.core.services.email import (
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.gmail.client import auth
from apps.core.services.email.gmail.client import provider as provider_module
from apps.core.services.email.sending.transport import ConnectFailed, ResponseLost
from apps.core.tests.gmail_api_helpers import (
    FakePost,
    gmail_error,
    send_response,
    token_response,
)
from apps.core.tests.services.gmail_api.provider.test_gmail_provider import GmailProviderTestCase


class AnswerTests(GmailProviderTestCase):
    CASES = (
        # (answer, exception class, signal kind, signal reason)
        (gmail_error(400, reason="badRequest"), PermanentEmailDeliveryError, SignalKind.NONE, "rejected"),
        (gmail_error(400, status_text="INVALID_ARGUMENT"), PermanentEmailDeliveryError, SignalKind.NONE, "rejected"),
        (gmail_error(400, reason="failedPrecondition"), PermanentEmailDeliveryError, SignalKind.BLOCKED, "permission"),
        (gmail_error(403, reason="rateLimitExceeded"), TransientEmailDeliveryError, SignalKind.THROTTLE, "throttled"),
        (
            gmail_error(403, details_reason="RATE_LIMIT_EXCEEDED"),
            TransientEmailDeliveryError,
            SignalKind.THROTTLE,
            "throttled",
        ),
        (
            gmail_error(403, reason="userRateLimitExceeded"),
            TransientEmailDeliveryError,
            SignalKind.THROTTLE,
            "throttled",
        ),
        (gmail_error(403, reason="dailyLimitExceeded"), TransientEmailDeliveryError, SignalKind.QUOTA, "project_quota"),
        (gmail_error(403, reason="domainPolicy"), PermanentEmailDeliveryError, SignalKind.BLOCKED, "permission"),
        (gmail_error(403, reason="insufficientPermissions"), PermanentEmailDeliveryError, SignalKind.BLOCKED, "auth"),
        (gmail_error(404), PermanentEmailDeliveryError, SignalKind.BLOCKED, "permission"),
        (gmail_error(408), TransientEmailDeliveryError, SignalKind.THROTTLE, "throttled"),
        (gmail_error(413), PermanentEmailDeliveryError, SignalKind.NONE, "rejected"),
        (
            gmail_error(429, reason="rateLimitExceeded", message="User-rate limit exceeded (Mail sending)"),
            TransientEmailDeliveryError,
            SignalKind.QUOTA,
            "daily_sending_limit",
        ),
        (
            gmail_error(429, message="Too many concurrent requests for user."),
            TransientEmailDeliveryError,
            SignalKind.THROTTLE,
            "concurrent_requests",
        ),
        (
            gmail_error(429, message="Too many requests: User-rate limit exceeded"),
            TransientEmailDeliveryError,
            SignalKind.QUOTA,
            "bandwidth",
        ),
        (gmail_error(429, message="Something else"), TransientEmailDeliveryError, SignalKind.THROTTLE, "throttled"),
        (gmail_error(500, reason="backendError"), UncertainEmailDeliveryError, SignalKind.UNCERTAIN, "server_error"),
        (gmail_error(502), UncertainEmailDeliveryError, SignalKind.UNCERTAIN, "server_error"),
        (gmail_error(503), UncertainEmailDeliveryError, SignalKind.UNCERTAIN, "server_error"),
        (gmail_error(504), UncertainEmailDeliveryError, SignalKind.UNCERTAIN, "server_error"),
        (ConnectFailed(), TransientEmailDeliveryError, SignalKind.NONE, "unreachable"),
        (ResponseLost(), UncertainEmailDeliveryError, SignalKind.UNCERTAIN, "response_lost"),
    )

    def test_each_answer_is_classified_with_its_signal(self):
        for answer, error_class, kind, reason in self.CASES:
            label = getattr(answer, "status", type(answer).__name__)
            with self.subTest(answer=label, reason=reason), self.assertRaises(error_class) as caught:
                auth.clear_access_token_cache()
                self.send(answer)
            self.assertIs(type(caught.exception), error_class)
            self.assertEqual((caught.exception.rate_signal.kind, caught.exception.rate_signal.reason), (kind, reason))

    def test_the_mail_sending_breaker_takes_the_retry_time_from_the_message(self):
        message = "User-rate limit exceeded (Mail sending). Retry after 2099-01-01T00:00:00.000Z"
        with self.assertRaises(TransientEmailDeliveryError) as caught:
            self.send(gmail_error(429, message=message))
        self.assertEqual(caught.exception.rate_signal.breaker_seconds, 3600)  # clamped to retry_after_max_seconds

    def test_a_concurrent_throttle_without_a_hint_pauses_for_the_settings_value(self):
        with self.assertRaises(TransientEmailDeliveryError) as caught:
            self.send(gmail_error(429, message="Too many concurrent requests for user"))
        self.assertEqual(caught.exception.rate_signal.retry_after, 1)

    def test_a_401_drops_the_token_and_a_second_with_a_fresh_token_blocks(self):
        with self.assertRaises(PermanentEmailDeliveryError) as caught:
            self.send(gmail_error(401, reason="authError"))
        # The token was minted for this send, so the grant itself is refused.
        self.assertEqual(caught.exception.rate_signal.reason, Reason.AUTH)
        self.post = FakePost(token_response(), send_response(), gmail_error(401)).install(self)
        provider = self.provider()
        provider.send(self.message())  # caches a token
        with self.assertRaises(TransientEmailDeliveryError) as caught:
            provider.send(self.message())  # the cached token is refused: refresh, not a breaker
        self.assertEqual(caught.exception.rate_signal.kind, SignalKind.NONE)
        self.post.answers = [token_response(), send_response()]
        provider.send(self.message())
        self.assertEqual([path for _host, path in self.post.paths()].count("/token"), 2)

    def test_a_throttle_keeps_the_token_and_a_refused_grant_drops_it(self):
        for answer, refreshed in (
            (gmail_error(403, reason="rateLimitExceeded"), False),
            (gmail_error(403, reason="insufficientPermissions"), True),
        ):
            with self.subTest(refreshed=refreshed):
                auth.clear_access_token_cache()
                self.post = FakePost(token_response(), answer, token_response(), send_response()).install(self)
                provider = self.provider()
                with self.assertRaises(Exception):  # noqa: B017 - the class is covered above
                    provider.send(self.message())
                provider.send(self.message())
                self.assertEqual([path for _host, path in self.post.paths()].count("/token"), 2 if refreshed else 1)

    def test_an_unexpected_error_after_the_callback_is_uncertain(self):
        self.post = FakePost(token_response(), RuntimeError("boom with a secret")).install(self)
        with self.assertLogs(provider_module.logger, level="ERROR") as logs:
            with self.assertRaises(UncertainEmailDeliveryError):
                self.provider().send(self.message())
        self.assertNotIn("secret", "\n".join(logs.output))

    def test_logs_carry_status_reason_and_ids_only(self):
        with self.assertLogs(provider_module.logger, level="INFO") as logs:
            self.send(send_response())
        self.assertIn("id=18c0ffee1234abcd", logs.output[0])
        self.assertIn("sent_label=True", logs.output[0])
        with (
            self.assertLogs(provider_module.logger, level="WARNING") as logs,
            self.assertRaises(TransientEmailDeliveryError),
        ):
            auth.clear_access_token_cache()
            self.send(gmail_error(403, reason="rateLimitExceeded", message="SENTINEL text"))
        self.assertIn("status=403 reason=rateLimitExceeded", logs.output[0])
        self.assertNotIn("SENTINEL", "\n".join(logs.output))

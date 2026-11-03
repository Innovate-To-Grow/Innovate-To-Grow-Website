"""``GmailProvider.send``: the request shape, what is refused before any token, the order of steps, and Gmail's
answers as classified errors with their rate signals."""

import email
from unittest.mock import patch

from django.test import TestCase

from apps.core.services.delivery_rates import Reason, SignalKind
from apps.core.services.email import (
    EmailAttachment,
    EmailMessage,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.gmail import auth, compose
from apps.core.services.email.gmail import provider as provider_module
from apps.core.services.email.gmail.access import credential_for, require_subject
from apps.core.services.email.gmail.provider import GmailProvider
from apps.core.services.email.mime import CREDENTIAL_MAIL_CLASS, MAIL_CLASS_HEADER
from apps.core.services.email.transport import ConnectFailed, ResponseLost
from apps.core.tests.gmail_api_helpers import (
    SUBJECT,
    TOKEN,
    FakePost,
    gmail_error,
    reset_gmail_state,
    send_response,
    stored_config,
    token_response,
)

SEND = ("gmail.googleapis.com", "/upload/gmail/v1/users/me/messages/send?uploadType=media")


class GmailProviderTestCase(TestCase):
    def setUp(self):
        reset_gmail_state()
        self.config = stored_config()

    def provider(self, **options):
        values = {
            "credential": credential_for(self.config),
            "subject": require_subject(self.config, SUBJECT),
            "from_email": SUBJECT,
            "from_name": "Innovate to Grow",
        }
        values.update(options)
        return GmailProvider(**values)

    def message(self, **fields):
        values = {"subject": "Hello", "to": ("someone@example.com",), "text_body": "Hi"}
        values.update(fields)
        return EmailMessage(**values)

    def send(self, *answers, message=None, **options):
        auth.clear_access_token_cache()
        self.post = FakePost(token_response(), *answers).install(self)
        return self.provider(**options).send(message or self.message())


class RequestShapeTests(GmailProviderTestCase):
    def test_raw_mime_is_uploaded_as_message_rfc822(self):
        built, original = [], compose.build_mime_message

        def build(*args, **kwargs):
            built.append(original(*args, **kwargs))
            return built[-1]

        with patch.object(compose, "build_mime_message", build):
            result = self.send(send_response())
        token_call, send_call = self.post.calls
        self.assertEqual((send_call["host"], send_call["path"]), SEND)
        self.assertEqual(send_call["headers"]["Content-Type"], "message/rfc822")
        self.assertEqual(send_call["headers"]["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(send_call["body"], compose.transport_bytes(built[0]))
        parsed = email.message_from_bytes(send_call["body"])
        self.assertEqual(parsed["From"], f"Innovate to Grow <{SUBJECT}>")
        self.assertEqual((result.provider, result.message_id), ("gmail", parsed["Message-ID"]))
        self.assertTrue(result.accepted)
        self.assertEqual(token_call["host"], "oauth2.googleapis.com")

    def test_credential_mail_is_tagged_and_the_tag_cannot_be_set_by_callers(self):
        self.send(send_response(), message=self.message(keep_sent_copy=False))
        parsed = email.message_from_bytes(self.post.calls[1]["body"])
        self.assertEqual(parsed[MAIL_CLASS_HEADER], CREDENTIAL_MAIL_CLASS)
        self.send(send_response())
        self.assertIsNone(email.message_from_bytes(self.post.calls[1]["body"])[MAIL_CLASS_HEADER])
        with self.assertRaises(PermanentEmailDeliveryError):
            self.send(send_response(), message=self.message(headers={"x-i2g-mail-class": "ordinary"}))

    def test_order_is_token_then_callback_then_post(self):
        order = []
        self.post = FakePost(token_response(), send_response()).install(self)
        original = self.post.__call__

        def recording(host, path, body, headers, *, timeout):
            order.append(path)
            return original(host, path, body, headers, timeout=timeout)

        with patch("apps.core.services.email.gmail.transport.post", recording):
            self.provider().send(self.message(), before_provider_call=lambda: order.append("callback"))
        self.assertEqual(order, ["/token", "callback", SEND[1]])

    def test_a_callback_exception_propagates_unclassified_and_nothing_is_posted(self):
        self.post = FakePost(token_response()).install(self)

        class ClaimLost(Exception):
            pass

        def refuse():
            raise ClaimLost()

        with self.assertRaises(ClaimLost):
            self.provider().send(self.message(), before_provider_call=refuse)
        self.assertEqual(self.post.paths(), [("oauth2.googleapis.com", "/token")])


class RefusedBeforeTheTokenTests(GmailProviderTestCase):
    def test_each_problem_is_permanent_and_no_token_is_requested(self):
        large = EmailAttachment("big.bin", b"x" * 2_000)
        cases = {
            "bcc": ({"message": self.message(bcc=("hidden@example.com",))}),
            "sender": ({"message": self.message(headers={"Sender": "other@g.ucmerced.edu"})}),
            "return-path": ({"message": self.message(headers={"Return-Path": "<other@g.ucmerced.edu>"})}),
            "resent": ({"message": self.message(headers={"Resent-From": "other@g.ucmerced.edu"})}),
            "from": ({"from_email": "other@g.ucmerced.edu"}),
            "recipients": ({"max_recipients": 1, "message": self.message(to=("a@example.com", "b@example.com"))}),
            "size": ({"max_message_bytes": 1_000, "message": self.message(attachments=(large,))}),
            "credential": ({"credential_mail": "refuse", "message": self.message(keep_sent_copy=False)}),
        }
        with patch.object(auth, "get_access_token") as token:
            for name, options in cases.items():
                options = dict(options)
                message = options.pop("message", self.message())
                with self.subTest(name), self.assertRaises(PermanentEmailDeliveryError):
                    self.provider(**options).send(message)
        token.assert_not_called()

    def test_settings_ceilings_bound_stored_limits(self):
        provider = self.provider(max_recipients=10_000, max_message_bytes=10**12)
        self.assertEqual((provider.max_recipients, provider.max_message_bytes), (500, 25_000_000))

    def test_invalid_stored_values_are_refused_at_construction(self):
        credential = credential_for(self.config)
        for field, value in (("service_account_email", "x@example.com"), ("key_id", "nope"), ("key_ref", "")):
            with self.subTest(field=field), self.assertRaises(PermanentEmailDeliveryError):
                self.provider(credential=auth.GmailCredential(**{**credential.__dict__, field: value}))


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

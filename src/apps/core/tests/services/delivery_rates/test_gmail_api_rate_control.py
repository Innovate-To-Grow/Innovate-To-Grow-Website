"""The Gmail API under the delivery-rate limiter: its costs, the daily-sending and bandwidth breakers, throttles,
Uncertain answers that keep their usage, refused credentials, and a cooldown group of its own."""

from datetime import timedelta

from django.test import TestCase

from apps.core.models import DeliveryRateState
from apps.core.services import delivery_rates as rates
from apps.core.services.email import (
    EmailMessage,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
    deliver_email,
)
from apps.core.services.email.exceptions import EmailRateDeferred
from apps.core.services.email.gmail import clear_access_token_cache
from apps.core.tests.gmail_api_helpers import (
    SUBJECT,
    FakePost,
    gmail_error,
    make_email_config,
    reset_gmail_state,
    send_response,
    stored_config,
    token_error,
    token_response,
)

from .helpers import Channel, FakeClock, set_policy

MAIL_SENDING = "User-rate limit exceeded (Mail sending)"


class GmailApiRateTests(TestCase):
    def setUp(self):
        reset_gmail_state()
        self.clock = FakeClock().install(self)
        self.config = stored_config()
        self.email = make_email_config()

    def send(self, *answers, to=("a@example.com",), cc=()):
        clear_access_token_cache()  # every send below starts with its own token answer
        self.post = FakePost(*answers).install(self)
        return deliver_email(EmailMessage(subject="Hi", to=to, cc=cc, text_body="Hi"), config=self.email)

    def state(self):
        return DeliveryRateState.objects.get(channel=Channel.GMAIL_API_SEND, identity=SUBJECT)

    def sends(self):
        return [call for call in self.post.calls if call["host"] == "gmail.googleapis.com"]

    def test_costs_count_recipients_and_external_ones_outside_the_internal_domain(self):
        set_policy(Channel.GMAIL_API_SEND, internal_domain="ucmerced.edu")
        self.send(token_response(), send_response(), to=("a@ucmerced.edu", "b@g.ucmerced.edu"), cc=("c@x.org",))
        bucket = self.state().usage_buckets.get()
        # Google counts only the primary domain as internal: its subdomains are external.
        self.assertEqual((bucket.total, bucket.external, bucket.messages), (3, 2, 1))

    def test_a_blank_internal_domain_counts_everyone_as_external(self):
        self.send(token_response(), send_response(), to=("a@ucmerced.edu", "b@x.org"))
        self.assertEqual(self.state().usage_buckets.get().external, 2)

    def test_the_mail_sending_429_opens_the_daily_sending_breaker_for_every_lane(self):
        with self.assertRaises(TransientEmailDeliveryError):
            self.send(token_response(), gmail_error(429, reason="rateLimitExceeded", message=MAIL_SENDING))
        for lane in (rates.Lane.TRANSACTIONAL, rates.Lane.BULK):
            with self.subTest(lane=lane), self.assertRaises(EmailRateDeferred) as caught:
                self.post = FakePost().install(self)
                deliver_email(
                    EmailMessage(subject="x", to=("a@example.com",), text_body="x"), config=self.email, lane=lane
                )
            self.assertEqual(caught.exception.reason, "breaker:daily_sending_limit")
            self.assertEqual(self.post.calls, [])
        state = self.state()
        self.assertEqual(state.breaker_reason, "daily_sending_limit")
        self.assertEqual(state.usage_buckets.get().total, 0)  # refused: not counted against the daily limit

    def test_the_bandwidth_429_opens_its_own_breaker_for_an_hour(self):
        with self.assertRaises(TransientEmailDeliveryError):
            self.send(token_response(), gmail_error(429, message="Too many requests: User-rate limit exceeded"))
        state = self.state()
        self.assertEqual(state.breaker_reason, "bandwidth")
        self.assertEqual(state.breaker_retry_at - self.clock.now(), timedelta(seconds=3600))

    def test_a_concurrent_429_is_a_short_cooldown(self):
        with self.assertRaises(TransientEmailDeliveryError):
            self.send(token_response(), gmail_error(429, message="Too many concurrent requests for user"))
        self.assertEqual(self.state().cooldown_until - self.clock.now(), timedelta(seconds=1))
        self.send(token_response(), send_response())  # an inline send waits the second out
        self.assertGreaterEqual(sum(self.clock.slept), 1)

    def test_server_errors_are_uncertain_and_keep_their_usage(self):
        for status in (500, 503):
            with self.subTest(status=status), self.assertRaises(UncertainEmailDeliveryError):
                self.clock.advance(60)
                self.send(token_response(), gmail_error(status))
        self.assertEqual(sum(bucket.total for bucket in self.state().usage_buckets.all()), 2)
        self.assertEqual(self.state().last_signal, rates.SignalKind.UNCERTAIN)

    def test_a_refused_delegation_blocks_until_the_config_is_saved(self):
        refused = token_error("unauthorized_client", "Unauthorized client or scope in request.")
        with self.assertRaises(PermanentEmailDeliveryError):
            self.send(refused)
        with self.assertRaises(EmailRateDeferred) as caught:
            self.send()  # the breaker holds the next send back; nothing reaches Google
        self.assertEqual(caught.exception.reason, "breaker:auth")
        self.assertEqual(self.post.calls, [])
        state = self.state()
        self.assertEqual(state.breaker_reason, rates.Reason.AUTH)
        with self.captureOnCommitCallbacks(execute=True):
            self.config.name = "Gmail (delegation fixed)"
            self.config.save()
        self.assertEqual(self.state().breaker_retry_at, self.clock.now())  # the next send probes at once
        self.send(token_response(), send_response())
        self.assertEqual(self.state().breaker_state, DeliveryRateState.BreakerState.CLOSED)

    def test_a_gmail_api_cooldown_does_not_hold_back_gmail_imap(self):
        with self.assertRaises(TransientEmailDeliveryError):
            self.send(token_response(), gmail_error(403, reason="userRateLimitExceeded"))
        imap = rates.imap_identity("imap.gmail.com", SUBJECT)
        self.assertNotEqual(rates.cooldown_group(Channel.GMAIL_IMAP, imap), self.state().cooldown_group)
        admission = rates.admit(Channel.GMAIL_IMAP, imap, max_wait=0)
        rates.release(admission)

"""Microsoft Graph under the delivery-rate limiter: sends, mailbox reads and the access check share one cooldown
group per mailbox, because Outlook limits each app and mailbox."""

from unittest.mock import patch

from django.test import TestCase

from apps.core.models import DeliveryRateState, EmailServiceConfig
from apps.core.services import delivery_rates as rates
from apps.core.services.email import (
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
    deliver_email,
)
from apps.core.services.email.exceptions import EmailRateDeferred
from apps.core.services.email.graph.mailbox import GraphMailboxReader, GraphReadBusy
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.test_email_graph import (
    CLIENT_ID,
    MAILBOX,
    TENANT_ID,
    GraphFixtureMixin,
    error_body,
    graph_response,
    make_provider,
    simple_message,
)
from apps.core.tests.services.test_graph_mailbox_reader import GET_TARGET, FakeGet, GraphReaderFixtureMixin

from ..helpers import FakeClock

RESOLVE = "apps.core.services.email.delivery.resolve_provider"
READER_MAILBOX = "i2g@contoso.com"


class GraphTrafficMixin(GraphFixtureMixin):
    """Scripted token and sendMail answers (``self.fake``) and mailbox reads (``self.get``); sends are allowed."""

    def setUp(self):
        super().setUp()
        self.get = FakeGet()
        patcher = patch(GET_TARGET, new=self.get)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.config = create_graph_config(
            scope=(MAILBOX, READER_MAILBOX), name="Graph", is_active=True, tenant_id=TENANT_ID, client_id=CLIENT_ID
        )


class GraphSendTests(GraphTrafficMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.clock = FakeClock().install(self)
        self.email = EmailServiceConfig(name="Mail", is_active=True, provider="graph", from_email=MAILBOX)
        patcher = patch(RESOLVE, side_effect=lambda config, **options: make_provider())
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, **overrides):
        return deliver_email(simple_message(**overrides), config=self.email)

    def state(self, channel="graph_send", mailbox=MAILBOX):
        return DeliveryRateState.objects.get(channel=channel, identity=mailbox)

    def test_a_send_counts_its_external_recipients_for_the_hourly_limits(self):
        self.send(to=("a@contoso.com", "b@sub.contoso.com", "c@example.org"))

        bucket = self.state().usage_buckets.get()
        self.assertEqual((bucket.total, bucket.external, bucket.messages), (3, 1, 1))

    def test_a_429_cools_down_every_graph_request_for_the_mailbox_for_the_retry_after(self):
        self.script(send=graph_response(429, headers={"retry-after": "120"}))

        with self.assertRaises(TransientEmailDeliveryError):
            self.send()
        with self.assertRaises(EmailRateDeferred) as caught:
            self.send()
        # Reading the same mailbox waits too (a new read state starts inside its group's cooldown).
        with self.assertRaises(GraphReadBusy):
            GraphMailboxReader(self.config, MAILBOX).list_messages("INBOX", 5)

        self.assertEqual(caught.exception.reason, "cooldown")
        self.assertGreaterEqual(caught.exception.retry_after, 119)
        self.assertEqual((len(self.fake.send_requests), self.get.calls), (1, []))

    def test_pushback_without_a_throttle_status_may_have_been_sent(self):
        self.script(send=graph_response(403, body=error_body("ApplicationThrottled")))

        with self.assertRaises(UncertainEmailDeliveryError) as caught:
            self.send()

        self.assertEqual((caught.exception.rate_signal.kind, caught.exception.rate_signal.uncertain), ("pause", True))
        self.assertEqual(self.state().usage_buckets.get().total, 1)  # possibly sent: still counted

    def test_a_busy_token_endpoint_pauses_sending(self):
        self.script(token=HttpResponse(429, {"retry-after": "30"}, b'{"error": "temporarily_unavailable"}'))

        with self.assertRaises(TransientEmailDeliveryError):
            self.send()

        state = self.state()
        self.assertEqual(state.last_signal, rates.SignalKind.PAUSE)
        self.assertEqual(self.fake.send_requests, [])

    def test_refused_credentials_open_the_auth_breaker_until_the_config_is_saved(self):
        refused = b'{"error": "invalid_client", "error_codes": [7000215]}'
        self.script(token=HttpResponse(401, {}, refused))

        for _attempt in range(2):
            with self.assertRaises(Exception):  # noqa: B017 - first a refusal, then a deferral
                self.send()

        self.assertEqual(self.state().breaker_reason, rates.Reason.AUTH)
        self.assertEqual(len(self.fake.token_requests), 1)

    def test_a_401_refreshes_a_cached_token_but_a_401_for_a_fresh_token_stops_sending(self):
        # Plan §6: a second 401 right after a fresh token means the grant is refused, not that the token expired.
        provider = make_provider()  # one credential, so the token cache applies across the sends
        patcher = patch(RESOLVE, side_effect=lambda config, **options: provider)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.script(send=[graph_response(202), graph_response(401), graph_response(401)])
        self.send()  # the token is now cached

        with self.assertRaises(TransientEmailDeliveryError) as cached:
            self.send()
        self.assertEqual(cached.exception.rate_signal.kind, rates.SignalKind.NONE)
        self.assertEqual(self.state().breaker_state, DeliveryRateState.BreakerState.CLOSED)

        with self.assertRaises(TransientEmailDeliveryError) as fresh:
            self.send()  # the 401 dropped the cached token, so this one was issued for the send
        self.assertEqual((fresh.exception.rate_signal.kind, fresh.exception.rate_signal.reason), ("blocked", "auth"))
        self.assertEqual(self.state().breaker_reason, rates.Reason.AUTH)
        self.assertEqual(len(self.fake.token_requests), 2)
        with self.assertRaises(EmailRateDeferred):
            self.send()  # stopped until the configuration is saved (or the timed probe)
        self.assertEqual(len(self.fake.send_requests), 3)


class GraphReadTests(GraphReaderFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.clock = FakeClock().install(self)

    def test_reads_are_paced_on_the_read_channel_and_held_back_during_a_cooldown(self):
        self.reader().list_messages("INBOX", 5)
        state = DeliveryRateState.objects.get(channel="graph_read", identity=READER_MAILBOX)
        self.assertEqual(state.last_signal, rates.SignalKind.OK)

        self.get.outcome = HttpResponse(429, {"retry-after": "60"}, b"")
        with self.assertRaises(Exception):  # noqa: B017 - the reader's own "busy" error
            self.reader().list_messages("INBOX", 5)
        calls = len(self.get.calls)
        with self.assertRaises(GraphReadBusy) as caught:
            self.reader().list_messages("INBOX", 5)

        self.assertEqual(len(self.get.calls), calls)
        self.assertGreaterEqual(caught.exception.retry_after, 59)
        self.assertIn("try again in about", str(caught.exception))

    def test_an_unreachable_graph_gives_the_read_slot_back(self):
        from apps.core.services.email.graph import transport

        self.get.outcome = transport.ConnectFailed()
        with self.assertRaises(Exception):  # noqa: B017
            self.reader().list_messages("INBOX", 5)

        state = DeliveryRateState.objects.get(channel="graph_read", identity=READER_MAILBOX)
        self.assertIsNone(state.tat)
        self.assertEqual(state.last_signal, "")

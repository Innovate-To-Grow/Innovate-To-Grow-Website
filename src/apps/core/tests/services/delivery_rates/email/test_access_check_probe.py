from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import DeliveryRateState
from apps.core.services import delivery_rates as rates
from apps.core.services.delivery_rates.runtime import context
from apps.core.services.email.graph.access_check.probes import Prober
from apps.core.services.email.graph.access_check.report import FAIL, SEND
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.delivery_rates.email.test_graph_rate_control import READER_MAILBOX, GraphTrafficMixin
from apps.core.tests.services.test_email_graph import (
    MAILBOX,
    error_body,
    graph_response,
)

from ..helpers import FakeClock


class AccessCheckProbeTests(GraphTrafficMixin, TestCase):
    def setUp(self):
        super().setUp()
        FakeClock().install(self)
        self.prober = Prober("token", timeout=5)

    def test_probes_microsoft_should_allow_are_admitted_on_their_channel(self):
        with patch("apps.core.services.email.graph.access_check.probes.admit", wraps=rates.admit) as admit:
            self.prober.folder(READER_MAILBOX, expect_allowed=True)
            self.prober.send_mime(MAILBOX)

        self.assertEqual(
            [call.args for call in admit.call_args_list],
            [("graph_read", READER_MAILBOX), ("graph_send", MAILBOX)],
        )
        self.assertEqual(DeliveryRateState.objects.get(channel="graph_send").last_signal, rates.SignalKind.OK)

    def test_probes_that_must_be_refused_record_nothing(self):
        self.get.outcome = HttpResponse(403, {}, error_body("ErrorAccessDenied"))
        self.script(send=graph_response(403, body=error_body("ErrorSendAsDenied")))
        with patch("apps.core.services.email.graph.access_check.probes.admit") as admit:
            self.prober.folder("deny@contoso.com", expect_allowed=False)
            self.prober.messages("deny@contoso.com", expect_allowed=False)
            self.prober.send_json(
                SEND, url_mailbox="deny@contoso.com", from_mailbox="deny@contoso.com", recipient=MAILBOX
            )

        admit.assert_not_called()
        self.assertFalse(DeliveryRateState.objects.exists())

    def test_a_probe_held_back_by_a_cooldown_is_reported_not_run(self):
        DeliveryRateState.objects.create(
            channel="graph_send",
            identity=MAILBOX,
            cooldown_group=f"graph:{MAILBOX}",
            cooldown_until=context.clock() + timedelta(minutes=5),
        )

        result = self.prober.send_mime(MAILBOX)

        self.assertEqual(result.outcome, FAIL)
        self.assertIn("run the check again in about", result.note)
        self.assertEqual(self.fake.send_requests, [])

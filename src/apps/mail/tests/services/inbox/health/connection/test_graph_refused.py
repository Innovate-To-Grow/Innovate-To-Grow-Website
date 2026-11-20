"""A Graph read held back because Microsoft refused the app's sign-in hides the account, like a refused Gmail login;
a read that is only paced or throttled keeps it listed."""

from django.test import SimpleTestCase

from apps.core.services.email.graph.mailbox import GraphReadBusy
from apps.mail.services.inbox.reading import graph_backend


class GraphRefusedSignInTests(SimpleTestCase):
    def test_an_auth_breaker_hold_is_a_refused_sign_in(self):
        busy = graph_backend._busy(GraphReadBusy(120, reason="breaker:auth"))

        self.assertTrue(busy.refused)
        self.assertEqual(busy.retry_after, 120)

    def test_pacing_and_throttles_are_not_refusals(self):
        for reason in ("", "pace", "breaker:throttle"):
            with self.subTest(reason=reason):
                self.assertFalse(graph_backend._busy(GraphReadBusy(30, reason=reason)).refused)

    def test_a_reason_is_optional(self):
        self.assertEqual(GraphReadBusy(5).reason, "")

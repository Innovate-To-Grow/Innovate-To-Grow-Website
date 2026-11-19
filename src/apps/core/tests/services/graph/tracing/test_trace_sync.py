"""One Message Trace sync: its gates, the token-roles pre-check, the lease, the request budget, the backoff after
Microsoft's answers, the state it saves and the precedence of what it writes."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailDeliveryTraceState, OutboundEmail
from apps.core.services.email.graph.tracing import sync_delivery
from apps.core.services.email.graph.tracing.matching import Verdict
from apps.core.services.email.graph.tracing.state import THROTTLE_CAP_SECONDS, acquire_lease, state_for
from apps.core.services.email.graph.tracing.windows import TraceRun
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings

from . import SENDER, TraceSetupMixin, token_response, token_with_roles, trace_page, trace_row

DeliveryStatus = OutboundEmail.DeliveryStatus
Permission = EmailDeliveryTraceState.Permission
LOGGER = "apps.core.services.email.graph.tracing.reader"


class SyncGateTests(TraceSetupMixin, TestCase):
    message_trace = False

    def test_with_message_trace_off_nothing_is_requested(self):
        self.sent()
        self.assertEqual(sync_delivery().status, "disabled")
        self.assertEqual(self.microsoft.requests, [])
        self.assertFalse(EmailDeliveryTraceState.objects.exists())

    def test_a_from_address_outside_the_send_scope_is_not_traced(self):
        self.config.message_trace_enabled = True
        self.config.save()
        self.config.mailbox_scopes.update(permission="read")

        outcome = sync_delivery()

        self.assertEqual(outcome.status, "inactive")
        self.assertEqual(self.microsoft.requests, [])
        self.assertIn("does not let the From address send", EmailDeliveryTraceState.objects.get().last_error)


class SyncTests(TraceSetupMixin, TestCase):
    def state(self):
        return EmailDeliveryTraceState.objects.get(sender=SENDER)

    def test_without_the_role_in_the_token_no_trace_request_is_made(self):
        self.microsoft.token = token_response(token=token_with_roles(("Mail.Send", "Mail.ReadWrite")))
        self.sent()

        outcome = sync_delivery()

        self.assertEqual((outcome.status, self.microsoft.traces, self.microsoft.tokens), ("not_permitted", [], 1))
        state = self.state()
        self.assertEqual(state.permission, Permission.NOT_PERMITTED)
        self.assertAlmostEqual((state.next_run_after - timezone.now()).total_seconds(), 6 * 3600, delta=60)
        self.assertEqual(sync_delivery().status, "waiting")  # the backoff holds
        self.assertEqual(self.microsoft.tokens, 1)

    def test_microsoft_refusing_the_trace_waits_six_hours(self):
        self.sent()
        self.microsoft.pages = [trace_page(status=401)]

        with self.assertLogs(LOGGER, level="WARNING"):
            outcome = sync_delivery()

        self.assertEqual(outcome.status, "not_permitted")
        state = self.state()
        self.assertEqual((state.permission, state.consecutive_failures), (Permission.NOT_PERMITTED, 1))
        self.assertIn("HTTP 401", state.last_error)

    def test_a_throttle_backs_off_doubling_up_to_an_hour(self):
        self.sent()
        self.microsoft.pages = [trace_page(status=429, headers={"retry-after": "10"})]
        delays = []
        for _round in range(4):
            EmailDeliveryTraceState.objects.update(next_run_after=None)
            with self.assertLogs(LOGGER, level="WARNING"):
                outcome = sync_delivery()
            delays.append(outcome.retry_after)

        self.assertEqual(outcome.status, "busy")
        self.assertEqual(delays, [300, 600, 1200, 2400])
        EmailDeliveryTraceState.objects.update(next_run_after=None, last_run_stats={"throttles": 7})
        with self.assertLogs(LOGGER, level="WARNING"):
            self.assertEqual(sync_delivery().retry_after, THROTTLE_CAP_SECONDS)
        self.assertEqual(self.state().last_error, "")  # a throttle is not a failure

    def test_a_held_lease_blocks_a_second_sync(self):
        self.sent()
        state_for(SENDER)
        self.assertIsNotNone(acquire_lease(SENDER, timezone.now(), 60))

        self.assertEqual(sync_delivery().status, "locked")
        self.assertEqual(self.microsoft.requests, [])

    def test_an_expired_lease_is_taken_over(self):
        self.sent()
        state_for(SENDER)
        acquire_lease(SENDER, timezone.now() - timedelta(hours=1), 60)

        self.assertEqual(sync_delivery().status, "ok")

    def test_the_request_budget_ends_the_run(self):
        self.sent()
        self.microsoft.pages = [trace_page([trace_row(message_id="<other@x>")], skiptoken="more")]

        with monitoring_settings(trace_max_requests_per_run=3):
            outcome = sync_delivery()

        self.assertEqual((outcome.status, len(self.microsoft.traces)), ("partial", 3))
        self.assertEqual(outcome.stats["requests"], 3)

    def test_success_saves_the_state_and_stamps_the_candidates(self):
        email = self.sent()
        quiet = self.sent(hours_ago=3, internet_message_id="<m2@ucmerced.edu>")
        self.microsoft.pages = [trace_page([trace_row(received=email.accepted_at)])]

        outcome = sync_delivery()

        self.assertEqual(outcome.status, "ok")
        state = self.state()
        self.assertEqual((state.permission, state.consecutive_failures, state.lease_token), (Permission.OK, 0, None))
        self.assertIsNotNone(state.last_success_at)
        self.assertEqual(state.last_run_stats["delivered"], 1)
        email.refresh_from_db()
        quiet.refresh_from_db()
        self.assertEqual((email.delivery_status, email.trace_status), (DeliveryStatus.DELIVERED, "delivered"))
        self.assertEqual((quiet.delivery_status, quiet.trace_status), (DeliveryStatus.UNKNOWN, ""))
        self.assertIsNotNone(quiet.trace_checked_at)

    def test_only_candidates_are_traced(self):
        self.sent(hours_ago=0.1)  # too new
        self.sent(hours_ago=49)  # given up
        self.sent(category="access_check")
        self.sent(delivery_status=DeliveryStatus.FAILURE_CONFIRMED)
        make_other = self.sent(mailbox="other@ucmerced.edu")

        self.assertEqual(sync_delivery().status, "ok")
        self.assertEqual(self.microsoft.traces, [])
        self.assertIsNone(OutboundEmail.objects.get(pk=make_other.pk).trace_checked_at)

    def test_a_trace_never_replaces_a_stronger_status(self):
        # What a bounce (or an earlier trace) saved while the window was read: the guarded write keeps the stronger.
        cases = (
            (DeliveryStatus.FAILURE_CONFIRMED, "delivered", DeliveryStatus.FAILURE_CONFIRMED),
            (DeliveryStatus.QUARANTINED, "delivered", DeliveryStatus.QUARANTINED),
            (DeliveryStatus.FAILURE_CONFIRMED, "filtered_as_spam", DeliveryStatus.FAILURE_CONFIRMED),
            (DeliveryStatus.DELIVERED, "failure_confirmed", DeliveryStatus.FAILURE_CONFIRMED),
            (DeliveryStatus.NO_BOUNCE, "delivered", DeliveryStatus.DELIVERED),
            (DeliveryStatus.DELAYED, "delivered", DeliveryStatus.DELIVERED),
        )
        run = TraceRun(reader=None, mailbox=SENDER, now=timezone.now(), budget=1)
        for existing, new, expected in cases:
            email = self.sent(delivery_status=existing)
            with self.subTest(existing=existing, new=new):
                run.write(email, Verdict(new, "raw"))
                email.refresh_from_db()
                self.assertEqual((email.delivery_status, email.trace_status), (expected, "raw"))
        not_accepted = self.sent(status=OutboundEmail.Status.FAILED, delivery_status=DeliveryStatus.NOT_APPLICABLE)
        run.write(not_accepted, Verdict(DeliveryStatus.DELIVERED, "delivered"))
        not_accepted.refresh_from_db()
        self.assertEqual((not_accepted.delivery_status, not_accepted.trace_status), ("not_applicable", ""))

    def test_a_trace_failure_overrides_no_bounce_and_pending_leaves_it(self):
        failed = self.sent(delivery_status=DeliveryStatus.NO_BOUNCE)
        waiting = self.sent(
            hours_ago=1.5, internet_message_id="<m2@ucmerced.edu>", delivery_status=DeliveryStatus.DELAYED
        )
        rows = [
            trace_row(status="failed", received=failed.accepted_at),
            trace_row("<m2@ucmerced.edu>", status="pending", received=waiting.accepted_at),
        ]
        self.microsoft.pages = [trace_page(rows)]

        sync_delivery()

        failed.refresh_from_db()
        waiting.refresh_from_db()
        self.assertEqual((failed.delivery_status, failed.trace_status), (DeliveryStatus.FAILURE_CONFIRMED, "failed"))
        self.assertEqual((waiting.delivery_status, waiting.trace_status), (DeliveryStatus.DELAYED, "pending"))

"""Email Monitoring → the Overview's delivery status card: Message Trace off (with its setup steps) or on, its "Sync
delivery status now" and the read-only "Check permissions" (Admins, POST only, the 30-second cooldown), and the
banner and chips that say "delivered" only with trace data."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.admin.service_credentials.microsoft_graph.permissions import TRACE_SETUP_STEPS
from apps.core.models import (
    BackgroundJob,
    EmailDeliveryTraceState,
    MicrosoftGraphAccessCheck,
    MicrosoftGraphPermissionCheck,
)
from apps.core.services.email.graph.tracing import DELIVERY_TRACE_JOB_KIND
from apps.core.tests.services.graph.tracing import SENDER, TraceSetupMixin
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.tests.admin.admin_access.refusal import assert_refused_to_member, make_member


class _CardCase(TraceSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = make_superuser()
        self.client.force_login(self.user)
        self.overview = reverse("admin:mail_email_monitoring")
        self.url = reverse("admin:mail_email_monitoring_bounce_processing")

    def card(self) -> str:
        html = self.client.get(self.overview).content.decode()
        start = html.index('id="monitor-delivery-trace"')
        return html[start : html.index("</section>", start)]

    def post(self, action: str) -> list[str]:
        response = self.client.post(self.url, {"action": action}, follow=True)
        self.assertEqual(response.redirect_chain, [(self.overview, 302)])
        return [str(message) for message in response.context["messages"]]


class TraceOffTests(_CardCase):
    message_trace = False

    def test_the_card_says_off_with_the_setup_steps_and_offers_only_check_permissions(self):
        card = self.card()

        self.assertIn("Message Trace: Off", card)
        for step in TRACE_SETUP_STEPS:
            self.assertIn(step, card)
        self.assertNotIn('value="trace"', card)
        self.assertIn('value="permissions"', card)
        self.assertIn("Permission check: not run yet", card)
        self.assertContains(self.client.get(self.overview), "Message Trace is off, so the site confirms no delivery")

    def test_sync_now_while_off_queues_nothing_and_says_why(self):
        self.assertIn("Message Trace delivery status is off", self.post("trace")[0])
        self.assertFalse(BackgroundJob.objects.filter(kind=DELIVERY_TRACE_JOB_KIND).exists())
        self.assertEqual(self.microsoft.requests, [])

    def test_check_permissions_records_a_read_only_check_and_cools_down(self):
        [first] = self.post("permissions")
        [second] = self.post("permissions")

        check = MicrosoftGraphPermissionCheck.objects.get()
        self.assertEqual(check.checked_by, self.user)
        self.assertIn("Permission check: granted", first)
        self.assertIn("wait", second)
        # Only the token request: the role is in the token, so one trace probe, and never a probe email.
        self.assertEqual(self.microsoft.tokens, 1)
        self.assertLessEqual(len(self.microsoft.traces), 1)
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())
        self.assertIn("Message Trace <strong>available</strong>", self.card())


class TraceOnTests(_CardCase):
    def test_before_the_first_sync_it_waits_and_offers_sync_now(self):
        card = self.card()

        self.assertIn("Message Trace: Waiting for the first sync", card)
        self.assertIn('value="trace"', card)
        self.assertNotIn(TRACE_SETUP_STEPS[0], card)
        self.assertContains(self.client.get(self.overview), "Delivery is shown only from Microsoft's message trace")

    def test_sync_now_queues_one_sync_and_makes_no_request(self):
        self.assertEqual(
            self.post("trace"), ["A delivery status sync was queued; the background worker runs it within a minute."]
        )
        self.post("trace")

        self.assertEqual(BackgroundJob.objects.filter(kind=DELIVERY_TRACE_JOB_KIND).count(), 1)
        self.assertEqual(self.microsoft.requests, [])

    def test_sync_now_during_a_backoff_says_how_long_it_waits(self):
        EmailDeliveryTraceState.objects.create(sender=SENDER, next_run_after=timezone.now() + timedelta(hours=1))

        self.assertIn("but it waits until", self.post("trace")[0])

    def test_each_state_shows_its_own_label(self):
        now = timezone.now()
        cases = (
            ({"permission": "not_permitted", "last_error": "no role"}, "Waiting for permission"),
            ({"last_run_stats": {"throttles": 1}, "next_run_after": now + timedelta(minutes=5)}, "Throttled"),
            ({"consecutive_failures": 2, "last_error": "Graph said no", "last_error_at": now}, "Last sync failed"),
            ({"last_success_at": now, "last_run_stats": {"requests": 2, "delivered": 3}}, "Message Trace: Running"),
        )
        for values, label in cases:
            with self.subTest(label=label):
                EmailDeliveryTraceState.objects.all().delete()
                EmailDeliveryTraceState.objects.create(sender=SENDER, last_run_finished_at=now, **values)
                card = self.card()
                self.assertIn(label, card)
                self.assertEqual("permission" in values, TRACE_SETUP_STEPS[0] in card)

    def test_the_last_sync_counts_are_shown(self):
        EmailDeliveryTraceState.objects.create(
            sender=SENDER,
            last_run_finished_at=timezone.now(),
            last_success_at=timezone.now(),
            last_run_stats={"requests": 2, "rows": 7, "checked": 5, "updated": 4, "delivered": 3, "junk": 1},
        )

        self.assertIn("2 requests, 7 trace rows read, 5 emails checked, 4 updated (3 delivered", self.card())


class AccessTests(_CardCase):
    message_trace = False

    def test_both_actions_are_post_only_and_need_an_admin(self):
        for action in ("trace", "permissions"):
            with self.subTest(action=action):
                self.assertEqual(self.client.get(self.url, {"action": action}).status_code, 405)
        member = make_member()
        for action in ("trace", "permissions"):
            with self.subTest(action=action):
                assert_refused_to_member(self, self.url, member, "post", data={"action": action})
        self.assertFalse(MicrosoftGraphPermissionCheck.objects.exists())
        self.assertEqual(self.microsoft.requests, [])

    def test_any_admin_may_check_permissions(self):
        staff = make_admin(email="mail@example.com")
        self.client.force_login(staff)

        self.post("permissions")

        self.assertEqual(MicrosoftGraphPermissionCheck.objects.get().checked_by, staff)

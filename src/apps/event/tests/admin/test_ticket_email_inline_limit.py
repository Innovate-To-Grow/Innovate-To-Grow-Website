"""Bulk ticket-email actions send inline, waiting for each delivery slot inside the request, so one request only
takes as many as the email channel's current rate sends in the inline request budget (``inline_batch_limit``)."""

from unittest.mock import patch

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.delivery_rates import Family, inline_batch_limit
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.delivery_rates.helpers import set_policy
from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket

LIMIT_TARGET = "apps.event.admin.registration.ticket_emails.inline_batch_limit"
SEND_TARGET = "apps.event.services.ticket.mail.send_ticket_email"
REFUSAL = "cannot be sent from one request"


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class InlineTicketEmailLimitTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        event = make_event()
        ticket = make_ticket(event)
        self.registrations = [
            make_registration(make_member(email=f"guest{index}@example.com"), event, ticket) for index in range(3)
        ]
        self.send_all_url = reverse("admin:event_eventregistration_send_all_ticket_emails")
        self.changelist_url = reverse("admin:event_eventregistration_changelist")
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email="i2g@contoso.com")

    def action_data(self, registrations):
        return {"action": "resend_ticket_email", ACTION_CHECKBOX_NAME: [str(r.pk) for r in registrations]}

    @patch(SEND_TARGET)
    def test_send_all_is_refused_when_the_batch_exceeds_the_current_rate(self, send):
        with patch(LIMIT_TARGET, return_value=2):
            response = self.client.post(self.send_all_url, follow=True)

        self.assertRedirects(response, self.changelist_url)
        self.assertContains(response, f"3 ticket emails {REFUSAL} at Microsoft Graph&#x27;s current send rate (limit 2")
        send.assert_not_called()

    @patch(SEND_TARGET)
    def test_send_all_goes_ahead_when_the_batch_fits(self, send):
        with patch(LIMIT_TARGET, return_value=3):
            response = self.client.post(self.send_all_url, follow=True)

        self.assertNotContains(response, REFUSAL)
        self.assertEqual(send.call_count, 3)

    @patch(SEND_TARGET)
    def test_the_multi_select_resend_action_obeys_the_same_limit(self, send):
        with patch(LIMIT_TARGET, return_value=2):
            refused = self.client.post(self.changelist_url, self.action_data(self.registrations), follow=True)
            allowed = self.client.post(self.changelist_url, self.action_data(self.registrations[:2]), follow=True)

        self.assertContains(refused, REFUSAL)
        self.assertNotContains(allowed, REFUSAL)
        self.assertEqual(send.call_count, 2)

    @patch(SEND_TARGET)
    def test_without_an_active_email_channel_nothing_is_limited(self, send):
        with patch(LIMIT_TARGET, return_value=None):
            self.client.post(self.send_all_url, follow=True)

        self.assertEqual(send.call_count, 3)

    def test_the_confirmation_page_warns_before_a_refused_send(self):
        with patch(LIMIT_TARGET, return_value=2):
            over = self.client.get(self.send_all_url)
        with patch(LIMIT_TARGET, return_value=3):
            within = self.client.get(self.send_all_url)

        self.assertContains(over, "one request can send at most 2 emails")
        self.assertNotContains(within, "can send at most")


class InlineBatchLimitTest(TestCase):
    """The burst plus one message per interval for ``waits.inline_request_budget_seconds`` (25 s)."""

    def test_graph_sends_its_burst_then_one_every_two_and_a_half_seconds(self):
        create_graph_config(scope=("i2g@contoso.com",), name="Graph", is_active=True)
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email="i2g@contoso.com")

        # 24 messages a minute (0.4 a second) for 25 s, plus the 3-message burst.
        self.assertEqual(inline_batch_limit(Family.EMAIL), 13)

    def test_ses_follows_its_known_limit(self):
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email="i2g@example.edu")
        unknown = inline_batch_limit(Family.EMAIL)

        set_policy("ses_send", provider_limit=14)
        self.assertEqual(unknown, 12)  # Smart starts at half of the 1/sec sandbox fallback: 0.45/sec
        self.assertEqual(inline_batch_limit(Family.EMAIL), 1 + 1 + int(25 * 14 * 0.9))

    def test_no_active_email_channel_means_no_limit(self):
        self.assertIsNone(inline_batch_limit(Family.EMAIL))

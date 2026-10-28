"""Bulk ticket-email actions send inline, so a rate-limited provider (Microsoft Graph) only takes small batches."""

from unittest.mock import patch

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket

LIMIT_TARGET = "apps.core.models.base.service_credentials.email.GRAPH_INLINE_BATCH_LIMIT"
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

    def use_provider(self, provider):
        EmailServiceConfig.objects.all().delete()
        EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider=provider, from_email="sender@example.com"
        )

    def action_data(self, registrations):
        return {"action": "resend_ticket_email", ACTION_CHECKBOX_NAME: [str(r.pk) for r in registrations]}

    @patch(SEND_TARGET)
    def test_send_all_is_refused_when_the_batch_exceeds_the_providers_limit(self, send):
        self.use_provider("graph")

        with patch(LIMIT_TARGET, 2):
            response = self.client.post(self.send_all_url, follow=True)

        self.assertRedirects(response, self.changelist_url)
        self.assertContains(
            response, f"3 ticket emails {REFUSAL} while Microsoft Graph is the email provider (limit 2)"
        )
        send.assert_not_called()

    @patch(SEND_TARGET)
    def test_send_all_goes_ahead_when_the_batch_fits(self, send):
        self.use_provider("graph")

        with patch(LIMIT_TARGET, 3):
            response = self.client.post(self.send_all_url, follow=True)

        self.assertNotContains(response, REFUSAL)
        self.assertEqual(send.call_count, 3)

    @patch(SEND_TARGET)
    def test_the_multi_select_resend_action_obeys_the_same_limit(self, send):
        self.use_provider("graph")

        with patch(LIMIT_TARGET, 2):
            refused = self.client.post(self.changelist_url, self.action_data(self.registrations), follow=True)
            allowed = self.client.post(self.changelist_url, self.action_data(self.registrations[:2]), follow=True)

        self.assertContains(refused, REFUSAL)
        self.assertNotContains(allowed, REFUSAL)
        self.assertEqual(send.call_count, 2)

    @patch(SEND_TARGET)
    def test_providers_without_a_limit_send_everything(self, send):
        for provider in ("ses", "smtp"):
            with self.subTest(provider):
                send.reset_mock()
                self.use_provider(provider)

                with patch(LIMIT_TARGET, 1):
                    response = self.client.post(self.send_all_url, follow=True)

                self.assertNotContains(response, REFUSAL)
                self.assertEqual(send.call_count, 3)

    @patch(SEND_TARGET)
    def test_without_any_email_config_nothing_is_limited(self, send):
        EmailServiceConfig.objects.all().delete()

        with patch(LIMIT_TARGET, 1):
            self.client.post(self.send_all_url, follow=True)

        self.assertEqual(send.call_count, 3)

    def test_the_confirmation_page_warns_before_a_refused_send(self):
        self.use_provider("graph")

        with patch(LIMIT_TARGET, 2):
            over = self.client.get(self.send_all_url)
        with patch(LIMIT_TARGET, 3):
            within = self.client.get(self.send_all_url)

        self.assertContains(over, "allows at most 2 emails per request")
        self.assertNotContains(within, "allows at most")

    def test_the_confirmation_page_has_no_warning_for_ses(self):
        self.use_provider("ses")

        with patch(LIMIT_TARGET, 1):
            response = self.client.get(self.send_all_url)

        self.assertNotContains(response, "allows at most")

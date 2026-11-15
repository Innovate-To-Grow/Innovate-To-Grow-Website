from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
from apps.core.services.email import (
    DeliveryResult,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
)
from apps.event.models import EventRegistration, Ticket
from apps.event.services.ticket.mail import _send_via_ses, send_ticket_email
from apps.event.services.ticket.message import _issue_ticket_login_link
from apps.event.tests.helpers import make_event, make_member
from apps.event.tests.services.tickets.mail.test_ticket_mail import _mock_config
from apps.mail.models import LoginLinkToken


class TicketLoginLinkIssuanceTest(TestCase):
    """Ticket emails issue unified LoginLinkToken rows scoped to the registration."""

    def setUp(self):
        self.member = make_member()
        self.event = make_event()
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)

    def test_issues_token_bound_to_registration_with_ticket_redirect(self):
        url = _issue_ticket_login_link(self.registration)

        token = LoginLinkToken.objects.get(registration=self.registration)
        self.assertEqual(token.member_id, self.member.pk)
        self.assertIsNone(token.campaign)
        self.assertEqual(token.redirect_path, "/event-registration?event=demo-day")
        self.assertIn(f"/login-link#token={token.token}", url)

    def test_validity_comes_from_event_config(self):
        self.event.ticket_login_validity_days = 5
        self.event.save(update_fields=["ticket_login_validity_days", "updated_at"])

        before = timezone.now() + timedelta(days=5)
        _issue_ticket_login_link(self.registration)
        after = timezone.now() + timedelta(days=5)

        token = LoginLinkToken.objects.get(registration=self.registration)
        self.assertGreaterEqual(token.expires_at, before)
        self.assertLessEqual(token.expires_at, after)

    def test_reissue_revokes_previous_token(self):
        _issue_ticket_login_link(self.registration)
        first = LoginLinkToken.objects.get(registration=self.registration)

        _issue_ticket_login_link(self.registration)

        first.refresh_from_db()
        self.assertTrue(first.is_expired)
        active = self.registration.login_tokens.filter(expires_at__gt=timezone.now())
        self.assertEqual(active.count(), 1)

    def test_reissue_creation_failure_rolls_back_previous_token_revocation(self):
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        with (
            patch(
                "apps.mail.services.tokens.login_links.create_login_link",
                side_effect=RuntimeError("token creation failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            _issue_ticket_login_link(self.registration)

        previous.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(
            list(self.registration.login_tokens.values_list("pk", flat=True)),
            [previous.pk],
        )

    def test_returns_empty_string_without_member(self):
        unsaved = EventRegistration(member=None, event=self.event, ticket=self.ticket)
        self.assertEqual(_issue_ticket_login_link(unsaved), "")

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_send_ticket_email_embeds_login_link(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)

        send_ticket_email(self.registration)

        token = LoginLinkToken.objects.get(registration=self.registration)
        html = mock_deliver.call_args.args[0].html_body
        self.assertIn(f"/login-link#token={token.token}", html)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_successful_resend_revokes_previous_login_link(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_deliver.return_value = DeliveryResult(provider="ses", message_id="ticket-1")
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        send_ticket_email(self.registration)

        previous.refresh_from_db()
        self.assertTrue(previous.is_expired)
        active = self.registration.login_tokens.filter(expires_at__gt=timezone.now())
        self.assertEqual(active.count(), 1)

    def test_registration_delete_cascades_tokens(self):
        _issue_ticket_login_link(self.registration)
        self.assertEqual(LoginLinkToken.objects.filter(registration=self.registration).count(), 1)

        registration_id = self.registration.pk
        self.registration.delete()
        self.assertEqual(LoginLinkToken.objects.filter(registration_id=registration_id).count(), 0)


class TicketSendRetryAfterTest(TestCase):
    @patch("apps.event.services.ticket.mail.deliver_email")
    def test_the_provider_error_keeps_the_retry_after_hint(self, deliver):
        deliver.side_effect = TransientEmailDeliveryError("throttled", retry_after=45.0)

        with self.assertRaises(ProviderDeliveryError) as caught:
            _send_via_ses(config=_mock_config(), mime_message=MagicMock(), raise_provider_errors=True)

        self.assertEqual((caught.exception.outcome, caught.exception.retry_after), ("transient", 45.0))
        self.assertIsInstance(caught.exception.__cause__, TransientEmailDeliveryError)

    @patch("apps.event.services.ticket.mail.deliver_email")
    def test_errors_without_a_hint_stay_without_one(self, deliver):
        deliver.side_effect = PermanentEmailDeliveryError("rejected")

        with self.assertRaises(ProviderDeliveryError) as caught:
            _send_via_ses(config=_mock_config(), mime_message=MagicMock(), raise_provider_errors=True)

        self.assertEqual(caught.exception.outcome, "permanent")
        self.assertIsNone(caught.exception.retry_after)

"""Tests for the typed confirmation on the send-all-ticket-emails flow."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class TicketEmailTypedConfirmationTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_confirmation_page_shows_event_name_instruction(self):
        event = make_event(name="Spring Demo Day")
        ticket = make_ticket(event)
        member = make_member(email="show-event@example.com")
        make_registration(member, event, ticket)

        response = self.client.get(reverse("admin:event_eventregistration_send_all_ticket_emails"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Spring Demo Day")
        self.assertContains(response, "confirm-input")
        self.assertContains(response, "confirm-send-btn")

    def test_post_without_confirmation_text_redirects_back(self):
        event = make_event(name="Reject Event")
        ticket = make_ticket(event)
        member = make_member(email="no-text@example.com")
        make_registration(member, event, ticket)

        response = self.client.post(
            reverse("admin:event_eventregistration_send_all_ticket_emails"),
            {},
            follow=True,
        )

        self.assertContains(response, "Confirmation text does not match event name")

    def test_wrong_confirmation_text_does_not_send(self):
        event = make_event(name="Correct Name")
        ticket = make_ticket(event)
        member = make_member(email="wrong-text@example.com")
        make_registration(member, event, ticket)

        response = self.client.post(
            reverse("admin:event_eventregistration_send_all_ticket_emails"),
            {"confirmation_text": "Wrong Name"},
            follow=True,
        )

        self.assertContains(response, "Confirmation text does not match event name")

    @patch("apps.event.services.ticket_mail.send_ticket_email")
    def test_empty_event_name_does_not_accept_empty_confirmation(self, mock_send):
        event = make_event(name="")
        ticket = make_ticket(event)
        member = make_member(email="empty-event-name@example.com")
        make_registration(member, event, ticket)

        response = self.client.post(
            reverse("admin:event_eventregistration_send_all_ticket_emails"),
            {"confirmation_text": ""},
            follow=True,
        )

        self.assertContains(response, "Confirmation text does not match event name")
        mock_send.assert_not_called()

    @patch("apps.event.services.ticket_mail.send_ticket_email")
    def test_correct_confirmation_text_sends_emails(self, mock_send):
        event = make_event(name="Exact Match Event")
        ticket = make_ticket(event)
        member = make_member(email="match@example.com")
        make_registration(member, event, ticket)

        response = self.client.post(
            reverse("admin:event_eventregistration_send_all_ticket_emails"),
            {"confirmation_text": "Exact Match Event"},
        )

        self.assertRedirects(response, reverse("admin:event_eventregistration_changelist"))
        mock_send.assert_called_once()

    @patch("apps.event.services.ticket_mail.send_ticket_email")
    @patch("apps.authn.services.email.send_email.senders.send_notification_email")
    def test_send_all_ticket_emails_does_not_notify_staff(self, mock_notify, mock_send):
        from apps.authn.models import ContactEmail, Member

        other_staff = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=other_staff, email_address="other-staff@example.com", email_type="primary", verified=True
        )

        event = make_event(name="Notify Event")
        ticket = make_ticket(event)
        member = make_member(email="notify-target@example.com")
        make_registration(member, event, ticket)

        response = self.client.post(
            reverse("admin:event_eventregistration_send_all_ticket_emails"),
            {"confirmation_text": "Notify Event"},
        )

        self.assertRedirects(response, reverse("admin:event_eventregistration_changelist"))
        mock_send.assert_called_once()
        mock_notify.assert_not_called()

    @patch("apps.event.services.ticket_mail.send_ticket_email")
    def test_empty_registrations_does_not_require_confirmation(self, mock_send):
        response = self.client.post(
            reverse("admin:event_eventregistration_send_all_ticket_emails"),
            {},
        )

        self.assertRedirects(response, reverse("admin:event_eventregistration_changelist"))
        mock_send.assert_not_called()

    def test_submit_button_is_disabled_by_default(self):
        event = make_event(name="Button Test")
        ticket = make_ticket(event)
        member = make_member(email="btn-test@example.com")
        make_registration(member, event, ticket)

        response = self.client.get(reverse("admin:event_eventregistration_send_all_ticket_emails"))

        self.assertContains(response, "disabled")
        self.assertContains(response, "confirm-send-btn")

"""Tests for core.admin.notifications.notify_staff_of_action."""

from unittest.mock import patch

from django.test import TestCase

from authn.models import ContactEmail, Member
from core.admin.notifications import notify_staff_of_action


class NotifyStaffOfActionTest(TestCase):
    def setUp(self):
        self.actor = Member.objects.create_user(
            password="testpass123", is_staff=True, first_name="Actor", last_name="User"
        )
        ContactEmail.objects.create(
            member=self.actor, email_address="actor@example.com", email_type="primary", verified=True
        )

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_sends_to_all_staff_excluding_actor(self, mock_send):
        staff1 = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=staff1, email_address="staff1@example.com", email_type="primary", verified=True
        )
        staff2 = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=staff2, email_address="staff2@example.com", email_type="primary", verified=True
        )

        notify_staff_of_action(
            actor=self.actor,
            action="Test Action",
            summary=[{"label": "Field", "value": "Value"}],
        )

        self.assertEqual(mock_send.call_count, 2)
        recipients = {call[1]["recipient"] for call in mock_send.call_args_list}
        self.assertIn("staff1@example.com", recipients)
        self.assertIn("staff2@example.com", recipients)
        self.assertNotIn("actor@example.com", recipients)

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_includes_actor_when_exclude_actor_false(self, mock_send):
        notify_staff_of_action(
            actor=self.actor,
            action="Test Action",
            summary=[],
            exclude_actor=False,
        )

        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args[1]["recipient"], "actor@example.com")

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_no_recipients_does_not_call_send(self, mock_send):
        notify_staff_of_action(
            actor=self.actor,
            action="Solo Action",
            summary=[],
        )

        mock_send.assert_not_called()

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_skips_inactive_staff(self, mock_send):
        inactive = Member.objects.create_user(password="testpass123", is_staff=True, is_active=False)
        ContactEmail.objects.create(
            member=inactive, email_address="inactive@example.com", email_type="primary", verified=True
        )

        notify_staff_of_action(
            actor=self.actor,
            action="Active Only",
            summary=[],
        )

        mock_send.assert_not_called()

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_skips_non_staff_users(self, mock_send):
        non_staff = Member.objects.create_user(password="testpass123", is_staff=False, is_active=True)
        ContactEmail.objects.create(
            member=non_staff, email_address="nonstaff@example.com", email_type="primary", verified=True
        )

        notify_staff_of_action(
            actor=self.actor,
            action="Staff Only",
            summary=[],
        )

        mock_send.assert_not_called()

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_subject_includes_action(self, mock_send):
        staff = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=staff, email_address="subject@example.com", email_type="primary", verified=True
        )

        notify_staff_of_action(
            actor=self.actor,
            action="Deleted Event: Demo Day",
            summary=[],
        )

        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["subject"], "[I2G Admin] Deleted Event: Demo Day")

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_context_includes_admin_url(self, mock_send):
        staff = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(member=staff, email_address="url@example.com", email_type="primary", verified=True)

        notify_staff_of_action(
            actor=self.actor,
            action="Changed Something",
            summary=[],
            admin_url="https://admin.example.com/change/",
        )

        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["context"]["admin_url"], "https://admin.example.com/change/")

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_context_includes_summary(self, mock_send):
        staff = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=staff, email_address="summary@example.com", email_type="primary", verified=True
        )

        summary = [{"label": "Name", "value": "Hello"}, {"label": "Status", "value": "Active"}]
        notify_staff_of_action(
            actor=self.actor,
            action="Test",
            summary=summary,
        )

        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["context"]["summary"], summary)

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_handles_send_exception_gracefully(self, mock_send):
        staff = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=staff, email_address="error@example.com", email_type="primary", verified=True
        )
        mock_send.side_effect = Exception("SMTP error")

        notify_staff_of_action(
            actor=self.actor,
            action="Error Action",
            summary=[],
        )

from unittest.mock import MagicMock, patch

from django.test import TestCase

from authn.models.security import EmailAuthChallenge
from authn.services.email.auth_mail import send_auth_code_email
from mail.models import SESAccount


class AuthMailTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        SESAccount.all_objects.all().hard_delete()
        self.account = SESAccount.objects.create(display_name="Innovate to Grow", is_active=True)

    @patch("authn.services.email.auth_mail.SESService")
    def test_send_auth_code_email_uses_ses_service(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service.send_message.return_value = {"id": "msg-1", "message_id": "msg-1"}
        mock_service_cls.return_value = mock_service

        send_auth_code_email(
            purpose=EmailAuthChallenge.Purpose.LOGIN,
            code="123456",
            email="student@example.com",
        )

        mock_service_cls.assert_called_once_with(self.account)
        kwargs = mock_service.send_message.call_args.kwargs
        self.assertEqual(kwargs["to"], "student@example.com")
        self.assertIn("login code", kwargs["subject"].lower())
        self.assertIn("123456", kwargs["body_html"])
        self.account.refresh_from_db()
        self.assertIsNotNone(self.account.last_used_at)

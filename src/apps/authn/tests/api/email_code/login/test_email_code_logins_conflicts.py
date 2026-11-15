from unittest.mock import patch

from apps.authn.models import ContactEmail, EmailAuthChallenge
from apps.authn.tests.api.email_code.login.test_email_code_logins import _EmailCodeAuthLoginCase


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value="654321")
class EmailCodeAuthLoginTests(_EmailCodeAuthLoginCase):
    def test_unified_email_auth_rejects_conflicting_contact_email(self, _mock_code, _mock_send):
        ContactEmail.objects.create(
            member=self.member,
            email_address="blocked@example.com",
            email_type="other",
            verified=False,
        )

        response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "blocked@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["email"], "This email cannot be used for registration.")
        self.assertEqual(EmailAuthChallenge.objects.count(), 0)

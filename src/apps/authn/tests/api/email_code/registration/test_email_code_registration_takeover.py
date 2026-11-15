from unittest.mock import patch

from apps.authn.models import EmailAuthChallenge
from apps.authn.tests.api.email_code.registration.test_email_code_registration_pending import (
    CODE,
    PURPOSE,
    _DeactivatedMemberCannotSelfReactivateCase,
    _run_admin_action,
)


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value=CODE)
class DeactivatedMemberCannotSelfReactivateTests(_DeactivatedMemberCannotSelfReactivateCase):
    def test_password_register_cannot_take_over_deactivated_member(self, _code, mock_send):
        response = self.client.post(
            "/authn/register/",
            {
                "email": "deactivated@example.com",
                "password": "NewStrongPass456!",
                "password_confirm": "NewStrongPass456!",
                "first_name": "Taken",
                "last_name": "Over",
                "organization": "Elsewhere",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["email"], ["Unable to register with this email address."])
        mock_send.assert_not_called()
        self.member.refresh_from_db()
        self.assertEqual((self.member.first_name, self.member.last_name), ("Dee", "Activated"))
        self.assertTrue(self.member.check_password("StrongPass123!"))
        self._assert_still_deactivated()

    def test_admin_reactivation_restores_login(self, _code, mock_send):
        _run_admin_action("activate_members", self.site_admin, self.member)

        self._request_code("deactivated@example.com")
        response = self._verify("deactivated@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertEqual(mock_send.call_args.kwargs["link_flow"], "auth")
        self.assertTrue(EmailAuthChallenge.objects.filter(member=self.member, purpose=PURPOSE.LOGIN).exists())

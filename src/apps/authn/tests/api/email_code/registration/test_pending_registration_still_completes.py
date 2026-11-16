from unittest.mock import patch

from apps.authn.models import ContactEmail, EmailAuthChallenge
from apps.authn.tests.api.email_code.registration.test_email_code_registration_pending import (
    CODE,
    EMAIL_AUTH_SOURCES,
    GENERIC_REQUEST_MESSAGE,
    PURPOSE,
    _EmailCodeFlowBase,
    _run_admin_action,
)


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value=CODE)
class PendingRegistrationStillCompletesTests(_EmailCodeFlowBase):
    """Genuine pending signups keep working through /login, /subscribe and event registration."""

    def test_new_email_registers_through_every_source(self, _code, mock_send):
        for source in EMAIL_AUTH_SOURCES:
            with self.subTest(source=source):
                email = f"new-{source}@example.com"
                extra = {"event": "spring-showcase"} if source == "event_registration" else {}

                request_response = self._request_code(email, source, **extra)

                self.assertEqual(request_response.status_code, 202)
                self.assertEqual(request_response.data["message"], GENERIC_REQUEST_MESSAGE)
                self.assertEqual(mock_send.call_args.kwargs["link_source"], source)
                member = ContactEmail.objects.get(email_address=email).member
                self.assertFalse(member.is_active)
                self.assertTrue(member.registration_pending)

                verify_response = self._verify(email)

                self.assertEqual(verify_response.status_code, 200)
                self.assertIn("access", verify_response.data)
                member.refresh_from_db()
                self.assertTrue(member.is_active)
                self.assertFalse(member.registration_pending)
                self.assertTrue(ContactEmail.objects.get(email_address=email).verified)

    def test_repeat_request_reuses_pending_member_then_completes(self, _code, mock_send):
        self._request_code("again@example.com", "subscribe")
        pending = ContactEmail.objects.get(email_address="again@example.com").member
        self._skip_resend_cooldown("again@example.com")

        self._request_code("again@example.com", "event_registration", event="spring-showcase")

        self.assertEqual(ContactEmail.objects.get(email_address="again@example.com").member_id, pending.pk)
        self.assertEqual(EmailAuthChallenge.objects.filter(member=pending, purpose=PURPOSE.REGISTER).count(), 2)
        self.assertEqual(self._verify("again@example.com").status_code, 200)
        pending.refresh_from_db()
        self.assertTrue(pending.is_active)

    def test_claimed_subscriber_contact_registers(self, _code, _send):
        ContactEmail.objects.create(email_address="subscriber@example.com", email_type="other", subscribe=True)

        self._request_code("subscriber@example.com", "subscribe")
        member = ContactEmail.objects.get(email_address="subscriber@example.com").member

        self.assertTrue(member.registration_pending)
        self.assertEqual(self._verify("subscriber@example.com").status_code, 200)

    def test_password_register_flow_sets_and_clears_pending(self, _code, _send):
        self.client.post(
            "/authn/register/",
            {
                "email": "password-signup@example.com",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
                "first_name": "Pass",
                "last_name": "Word",
                "organization": "Individual",
            },
            format="json",
        )
        member = ContactEmail.objects.get(email_address="password-signup@example.com").member
        self.assertTrue(member.registration_pending)
        self._skip_resend_cooldown("password-signup@example.com")

        resend = self.client.post(
            "/authn/register/resend-code/", {"email": "password-signup@example.com"}, format="json"
        )
        verify = self._verify("password-signup@example.com", "/authn/register/verify-code/")

        self.assertEqual(resend.status_code, 202)
        self.assertEqual(verify.status_code, 200)
        member.refresh_from_db()
        self.assertTrue(member.is_active)
        self.assertFalse(member.registration_pending)

    def test_full_lifecycle_register_then_deactivate_then_blocked(self, _code, mock_send):
        self._request_code("lifecycle@example.com", "subscribe")
        self.assertEqual(self._verify("lifecycle@example.com").status_code, 200)
        member = ContactEmail.objects.get(email_address="lifecycle@example.com").member
        _run_admin_action("deactivate_members", self.site_admin, member)
        mock_send.reset_mock()

        request_response = self._request_code("lifecycle@example.com")
        verify_response = self._verify("lifecycle@example.com")

        self.assertEqual(request_response.status_code, 202)
        mock_send.assert_not_called()
        self.assertEqual(verify_response.status_code, 400)
        member.refresh_from_db()
        self.assertFalse(member.is_active)

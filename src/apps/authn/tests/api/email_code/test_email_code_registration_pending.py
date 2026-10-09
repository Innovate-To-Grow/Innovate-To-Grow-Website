"""Pending self-service signups vs admin-deactivated members in the public email-code flows.

Only a never-activated signup (``Member.registration_pending``) may be activated by proving
email ownership. An account an admin deactivated gets the flow's generic responses, nothing is
sent, and no code, old or new, brings it back.
"""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from rest_framework.test import APITestCase

from apps.authn.admin.members.member import MemberAdmin
from apps.authn.constants import VERIFICATION_INVALID
from apps.authn.models import ContactEmail, EmailAuthChallenge
from apps.authn.services import get_pending_registration_member, is_deactivated_member_email, issue_email_challenge

Member = get_user_model()

CODE = "654321"
GENERIC_REQUEST_MESSAGE = "Check your email for a verification code."
EMAIL_AUTH_SOURCES = ("login", "subscribe", "event_registration")
PURPOSE = EmailAuthChallenge.Purpose


def _run_admin_action(action: str, admin_user, member) -> None:
    request = RequestFactory().post("/admin/authn/member/")
    request.user = admin_user
    request.session = {}
    request._messages = FallbackStorage(request)
    getattr(MemberAdmin(Member, AdminSite()), action)(request, Member.objects.filter(pk=member.pk))
    member.refresh_from_db()


class _EmailCodeFlowBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.site_admin = Member.objects.create_superuser(
            password="AdminPass123!", first_name="Site", last_name="Admin"
        )

    def _request_code(self, email: str, source: str = "login", **extra):
        return self.client.post(
            "/authn/email-auth/request-code/", {"email": email, "source": source, **extra}, format="json"
        )

    def _verify(self, email: str, path: str = "/authn/email-auth/verify-code/"):
        return self.client.post(path, {"email": email, "code": CODE}, format="json")

    @staticmethod
    def _skip_resend_cooldown(email: str) -> None:
        EmailAuthChallenge.objects.filter(target_email=email).update(last_sent_at=None)


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value=CODE)
class DeactivatedMemberCannotSelfReactivateTests(_EmailCodeFlowBase):
    """The reported bug: admin deactivates -> request-code issued REGISTER -> verify reactivated."""

    def setUp(self):
        super().setUp()
        self.member = Member.objects.create_user(
            password="StrongPass123!", first_name="Dee", last_name="Activated", is_active=True
        )
        self.contact = ContactEmail.objects.create(
            member=self.member, email_address="deactivated@example.com", email_type="primary", verified=True
        )
        _run_admin_action("deactivate_members", self.site_admin, self.member)
        self.assertFalse(self.member.is_active)
        self.assertFalse(self.member.registration_pending)

    def _assert_still_deactivated(self):
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertFalse(self.member.registration_pending)

    def test_request_code_answers_generically_and_sends_nothing_for_every_source(self, _code, mock_send):
        members_before = Member.objects.count()
        for source in EMAIL_AUTH_SOURCES:
            with self.subTest(source=source):
                extra = {"event": "spring-showcase"} if source == "event_registration" else {}
                response = self._request_code("deactivated@example.com", source, **extra)
                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.data["message"], GENERIC_REQUEST_MESSAGE)

        mock_send.assert_not_called()
        self.assertFalse(EmailAuthChallenge.objects.filter(member=self.member).exists())
        self.assertEqual(Member.objects.count(), members_before)
        self._assert_still_deactivated()

    def test_request_code_response_matches_an_active_account(self, _code, _send):
        active = Member.objects.create_user(password="StrongPass123!", is_active=True)
        ContactEmail.objects.create(
            member=active, email_address="active@example.com", email_type="primary", verified=True
        )

        deactivated_response = self._request_code("DeActivated@Example.com ")
        active_response = self._request_code("active@example.com")

        self.assertEqual(deactivated_response.status_code, active_response.status_code)
        self.assertEqual(deactivated_response.data, active_response.data)

    def test_verify_with_any_code_is_rejected(self, _code, _send):
        self._request_code("deactivated@example.com")

        response = self._verify("deactivated@example.com")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], [VERIFICATION_INVALID])
        self.assertNotIn("access", response.data)
        self._assert_still_deactivated()

    def test_unverified_email_of_deactivated_member_is_also_blocked(self, _code, mock_send):
        # e.g. an imported member whose sheet row had no verified flag.
        imported = Member.objects.create_user(first_name="Imp", last_name="Orted", is_active=False)
        ContactEmail.objects.create(
            member=imported, email_address="imported@example.com", email_type="primary", verified=False
        )

        response = self._request_code("imported@example.com", "subscribe")
        verify_response = self._verify("imported@example.com")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["message"], GENERIC_REQUEST_MESSAGE)
        self.assertEqual(verify_response.status_code, 400)
        mock_send.assert_not_called()
        imported.refresh_from_db()
        self.assertFalse(imported.is_active)

    def test_register_challenge_issued_before_deactivation_cannot_activate(self, _code, _send):
        signup = Member.objects.create_user(is_active=False, registration_pending=True)
        ContactEmail.objects.create(member=signup, email_address="mid-signup@example.com", email_type="primary")
        self._request_code("mid-signup@example.com")
        challenge = EmailAuthChallenge.objects.get(member=signup, purpose=PURPOSE.REGISTER)

        _run_admin_action("deactivate_members", self.site_admin, signup)
        self.assertFalse(signup.registration_pending)

        for path in ("/authn/email-auth/verify-code/", "/authn/register/verify-code/"):
            with self.subTest(path=path):
                response = self._verify("mid-signup@example.com", path)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("access", response.data)

        signup.refresh_from_db()
        challenge.refresh_from_db()
        self.assertFalse(signup.is_active)
        self.assertNotEqual(challenge.status, EmailAuthChallenge.Status.CONSUMED)

    def test_stale_register_challenge_for_deactivated_member_is_rejected(self, _code, _send):
        # A REGISTER code issued to this member before the fix (when any inactive member counted
        # as pending) must not complete now.
        issue_email_challenge(member=self.member, purpose=PURPOSE.REGISTER, target_email="deactivated@example.com")

        response = self._verify("deactivated@example.com")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], [VERIFICATION_INVALID])
        self._assert_still_deactivated()

    def test_register_resend_code_treats_deactivated_like_unknown_email(self, _code, mock_send):
        deactivated = self.client.post(
            "/authn/register/resend-code/", {"email": "deactivated@example.com"}, format="json"
        )
        unknown = self.client.post("/authn/register/resend-code/", {"email": "nobody@example.com"}, format="json")

        self.assertEqual(deactivated.status_code, 400)
        self.assertEqual(deactivated.data, unknown.data)
        mock_send.assert_not_called()
        self._assert_still_deactivated()

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


class RegistrationPendingMarkerTests(TestCase):
    def setUp(self):
        self.site_admin = Member.objects.create_superuser(
            password="AdminPass123!", first_name="Site", last_name="Admin"
        )
        self.pending = Member.objects.create_user(is_active=False, registration_pending=True)
        ContactEmail.objects.create(member=self.pending, email_address="pending@example.com", email_type="primary")

    def test_lookups_distinguish_pending_from_deactivated(self):
        deactivated = Member.objects.create_user(is_active=False)
        ContactEmail.objects.create(member=deactivated, email_address="off@example.com", email_type="primary")

        self.assertEqual(get_pending_registration_member("Pending@Example.com"), self.pending)
        self.assertIsNone(get_pending_registration_member("off@example.com"))
        self.assertTrue(is_deactivated_member_email("OFF@example.com"))
        self.assertFalse(is_deactivated_member_email("pending@example.com"))
        self.assertFalse(is_deactivated_member_email(""))
        self.assertFalse(is_deactivated_member_email("nobody@example.com"))

    def test_any_activation_clears_the_marker(self):
        self.pending.is_active = True
        self.pending.save(update_fields=["is_active"])

        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_active)
        self.assertFalse(self.pending.registration_pending)

        # Re-deactivating through the change form (a plain save) leaves it non-pending.
        self.pending.is_active = False
        self.pending.save()
        self.assertIsNone(get_pending_registration_member("pending@example.com"))

    def test_admin_activate_action_clears_the_marker(self):
        _run_admin_action("activate_members", self.site_admin, self.pending)

        self.assertTrue(self.pending.is_active)
        self.assertFalse(self.pending.registration_pending)

    def test_admin_deactivate_action_ends_a_pending_signup(self):
        _run_admin_action("deactivate_members", self.site_admin, self.pending)

        self.assertFalse(self.pending.is_active)
        self.assertFalse(self.pending.registration_pending)
        self.assertIsNone(get_pending_registration_member("pending@example.com"))

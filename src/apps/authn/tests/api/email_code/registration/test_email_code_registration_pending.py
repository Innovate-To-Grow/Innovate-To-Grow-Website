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
from django.test import RequestFactory
from rest_framework.test import APITestCase

from apps.authn.admin.members.member.admin import MemberAdmin
from apps.authn.constants import VERIFICATION_INVALID
from apps.authn.models import ContactEmail, EmailAuthChallenge
from apps.authn.services import issue_email_challenge

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


class _DeactivatedMemberCannotSelfReactivateCase(_EmailCodeFlowBase):
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


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value=CODE)
class DeactivatedMemberCannotSelfReactivateTests(_DeactivatedMemberCannotSelfReactivateCase):
    """The reported bug: admin deactivates -> request-code issued REGISTER -> verify reactivated."""

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

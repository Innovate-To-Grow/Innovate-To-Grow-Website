"""Tests for AdminInvitation Django admin behavior."""

from unittest.mock import ANY, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.admin.security.invitation import AdminInvitationAdmin
from apps.authn.models import AdminInvitation
from apps.authn.models.members.member import Member


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class AdminInvitationAdminTests(TestCase):
    def setUp(self):
        self.staff = Member.objects.create_superuser(
            password="StrongPass123!",
            first_name="Admin",
            last_name="User",
            is_active=True,
        )
        self.client.force_login(self.staff)

    def _create_invitation(self, email="invite@example.com", **kwargs):
        defaults = {
            "email": email,
            "token": AdminInvitation.generate_token(),
            "status": AdminInvitation.Status.PENDING,
            "expires_at": timezone.now() + timezone.timedelta(days=7),
            "invited_by": self.staff,
        }
        defaults.update(kwargs)
        return AdminInvitation.objects.create(**defaults)

    @patch("apps.authn.services.email.send_admin_invitation_email")
    def test_admin_add_sends_invitation_email(self, mock_send):
        # Sent once the admin's transaction commits (no lock is held across the provider call).
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("admin:authn_admininvitation_add"),
                {
                    "email": "New.Admin@Example.COM ",
                    "role": AdminInvitation.Role.ADMIN,
                    "message": "Welcome.",
                    "_save": "Save",
                },
            )

        self.assertEqual(response.status_code, 302)
        invitation = AdminInvitation.objects.get(email="new.admin@example.com")
        self.assertEqual(invitation.invited_by, self.staff)
        self.assertEqual(invitation.status, AdminInvitation.Status.PENDING)
        self.assertTrue(invitation.token)
        self.assertGreater(invitation.expires_at, timezone.now())
        mock_send.assert_called_once_with(invitation=invitation, request=ANY)

    @patch("apps.authn.services.email.send_admin_invitation_email")
    def test_admin_add_cancels_previous_pending_invitation_for_email(self, mock_send):
        old = self._create_invitation(email="invite@example.com")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("admin:authn_admininvitation_add"),
                {
                    "email": "INVITE@example.com",
                    "role": AdminInvitation.Role.ADMIN,
                    "message": "",
                    "_save": "Save",
                },
            )

        self.assertEqual(response.status_code, 302)
        old.refresh_from_db()
        self.assertEqual(old.status, AdminInvitation.Status.CANCELLED)
        self.assertEqual(AdminInvitation.objects.filter(email__iexact="invite@example.com").count(), 2)
        mock_send.assert_called_once()

    @patch("apps.authn.services.email.send_admin_invitation_email")
    def test_resend_action_sends_only_valid_pending_invitations(self, mock_send):
        valid = self._create_invitation(email="valid@example.com")
        expired = self._create_invitation(
            email="expired@example.com",
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        accepted = self._create_invitation(email="accepted@example.com", status=AdminInvitation.Status.ACCEPTED)

        request = RequestFactory().post("/")
        request.user = self.staff
        request.session = self.client.session
        request._messages = FallbackStorage(request)
        admin_obj = AdminInvitationAdmin(AdminInvitation, AdminSite())
        admin_obj.resend_invitations(
            request, AdminInvitation.objects.filter(pk__in=[valid.pk, expired.pk, accepted.pk])
        )

        mock_send.assert_called_once_with(invitation=valid, request=request)
        expired.refresh_from_db()
        self.assertEqual(expired.status, AdminInvitation.Status.EXPIRED)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class AdminInvitationAccessTests(TestCase):
    """Every Admin manages invitations; the link is shown to the Admin who sent it; a regular member never reaches the page."""

    def setUp(self):
        self.admin = Member.objects.create_user(
            password="StrongPass123!", first_name="Any", last_name="Admin", is_active=True, is_staff=True
        )
        self.invitation = AdminInvitation.objects.create(
            email="invitee@example.com",
            token=AdminInvitation.generate_token(),
            status=AdminInvitation.Status.PENDING,
            expires_at=timezone.now() + timezone.timedelta(days=7),
            invited_by=self.admin,
        )
        self.change_url = reverse("admin:authn_admininvitation_change", args=[self.invitation.pk])

    def test_the_inviting_admin_sees_the_link_and_any_admin_may_add_change_and_delete(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.change_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.invitation.token)
        self.assertEqual(self.client.get(reverse("admin:authn_admininvitation_add")).status_code, 200)

        model_admin = AdminInvitationAdmin(AdminInvitation, AdminSite())
        request = RequestFactory().get("/")
        request.user = self.admin
        self.assertTrue(model_admin.has_add_permission(request))
        self.assertTrue(model_admin.has_change_permission(request, self.invitation))
        self.assertTrue(model_admin.has_delete_permission(request, self.invitation))

        response = self.client.post(
            reverse("admin:authn_admininvitation_delete", args=[self.invitation.pk]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AdminInvitation.objects.filter(pk=self.invitation.pk).exists())

    def test_a_regular_member_is_sent_to_the_admin_login(self):
        member = Member.objects.create_user(password="StrongPass123!", first_name="Reg", last_name="Ular")
        self.client.force_login(member)

        response = self.client.get(self.change_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        self.assertNotIn(self.invitation.token, response.content.decode())

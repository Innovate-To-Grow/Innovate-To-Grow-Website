"""Tests for AcceptInvitationView (Django view, not DRF)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from authn.models import ContactEmail
from authn.models.members.admin_invitation import AdminInvitation

Member = get_user_model()


class AcceptInvitationViewTests(TestCase):
    # noinspection PyMethodMayBeStatic
    def _create_invitation(self, email="invite@example.com", role=AdminInvitation.Role.ADMIN, **kwargs):
        defaults = {
            "email": email,
            "token": AdminInvitation.generate_token(),
            "role": role,
            "status": AdminInvitation.Status.PENDING,
            "expires_at": timezone.now() + timezone.timedelta(days=7),
        }
        defaults.update(kwargs)
        return AdminInvitation.objects.create(**defaults)

    def test_get_valid_invitation_renders_form(self):
        invitation = self._create_invitation()
        response = self.client.get(f"/authn/invite/{invitation.token}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invite@example.com")

    def test_get_invalid_token_returns_error(self):
        response = self.client.get("/authn/invite/nonexistent-token/")
        self.assertEqual(response.status_code, 400)

    def test_get_expired_invitation_returns_error(self):
        invitation = self._create_invitation(
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        response = self.client.get(f"/authn/invite/{invitation.token}/")
        self.assertEqual(response.status_code, 400)

    def test_get_cancelled_invitation_returns_error(self):
        invitation = self._create_invitation(status=AdminInvitation.Status.CANCELLED)
        response = self.client.get(f"/authn/invite/{invitation.token}/")
        self.assertEqual(response.status_code, 400)

    def test_post_creates_staff_member(self):
        invitation = self._create_invitation()
        response = self.client.post(
            f"/authn/invite/{invitation.token}/",
            {
                "email": "invite@example.com",
                "first_name": "Staff",
                "last_name": "User",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        member = ContactEmail.objects.get(email_address="invite@example.com").member
        self.assertTrue(member.is_staff)
        self.assertTrue(member.is_active)

    def test_post_existing_member_upgrades_to_staff(self):
        existing = Member.objects.create_user(
            password="StrongPass123!",
            is_staff=False,
        )
        ContactEmail.objects.create(
            member=existing, email_address="invite@example.com", email_type="primary", verified=True
        )
        invitation = self._create_invitation(email="invite@example.com")
        response = self.client.post(
            f"/authn/invite/{invitation.token}/",
            {
                "email": "invite@example.com",
                "first_name": "Ignored",
                "last_name": "Ignored",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        existing.refresh_from_db()
        self.assertTrue(existing.is_staff)

    def test_invitation_marked_accepted_after_success(self):
        invitation = self._create_invitation()
        self.client.post(
            f"/authn/invite/{invitation.token}/",
            {
                "email": invitation.email,
                "first_name": "Accepted",
                "last_name": "User",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, AdminInvitation.Status.ACCEPTED)
        self.assertIsNotNone(invitation.accepted_by)
        self.assertIsNotNone(invitation.accepted_at)

    def test_post_password_mismatch_rejected(self):
        invitation = self._create_invitation()
        member_count_before = Member.objects.count()
        response = self.client.post(
            f"/authn/invite/{invitation.token}/",
            {
                "email": invitation.email,
                "first_name": "Mis",
                "last_name": "Match",
                "password1": "StrongPass123!",
                "password2": "DifferentPass456!",
            },
        )
        # Should re-render form, not create member
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Member.objects.count(), member_count_before)

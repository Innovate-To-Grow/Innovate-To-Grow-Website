"""An invitation never reactivates a deactivated account into an Admin (the token holder is unauthenticated)."""

from unittest.mock import patch

from apps.authn.models import ContactEmail
from apps.authn.models.members.admin_invitation import AdminInvitation
from apps.authn.tests.admin.invitations.test_invitation import Member, _AcceptInvitationViewCase
from apps.authn.views.admin.invitation.membership import InvitationMembershipMixin


class InactiveMemberInvitationTests(_AcceptInvitationViewCase):
    def _inactive_invitee(self):
        existing = Member.objects.create_user(password="StrongPass123!", is_active=False, is_staff=False)
        ContactEmail.objects.create(
            member=existing, email_address="invite@example.com", email_type="primary", verified=True
        )
        return existing, self._create_invitation(email="invite@example.com")

    def test_get_for_a_deactivated_member_explains_and_offers_no_upgrade(self):
        existing, invitation = self._inactive_invitee()

        response = self.client.get(f"/authn/invite/{invitation.token}/")

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "it is deactivated", status_code=403)
        self.assertNotContains(response, "Grant admin access", status_code=403)

    def test_post_never_reactivates_a_deactivated_member_into_an_admin(self):
        """The token holder is unauthenticated: an Admin must reactivate the account first."""
        existing, invitation = self._inactive_invitee()

        response = self.client.post(f"/authn/invite/{invitation.token}/")

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Ask an Admin to reactivate the account", status_code=403)
        existing.refresh_from_db()
        self.assertFalse(existing.is_active)
        self.assertFalse(existing.is_staff)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, AdminInvitation.Status.PENDING)

    def test_post_refuses_a_member_deactivated_after_the_lookup(self):
        """The upgrade re-reads the account under a lock, so a deactivation racing the POST still wins."""
        existing = Member.objects.create_user(password="StrongPass123!", is_active=True)
        ContactEmail.objects.create(
            member=existing, email_address="invite@example.com", email_type="primary", verified=True
        )
        invitation = self._create_invitation(email="invite@example.com")
        stale = Member.objects.get(pk=existing.pk)
        Member.objects.filter(pk=existing.pk).update(is_active=False)

        with patch.object(InvitationMembershipMixin, "_get_verified_member", return_value=stale):
            response = self.client.post(f"/authn/invite/{invitation.token}/")

        self.assertEqual(response.status_code, 403)
        existing.refresh_from_db()
        self.assertFalse(existing.is_staff)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, AdminInvitation.Status.PENDING)

    def test_after_reactivation_the_same_invitation_makes_an_admin(self):
        existing, invitation = self._inactive_invitee()
        existing.is_active = True
        existing.save()

        response = self.client.post(f"/authn/invite/{invitation.token}/")

        self.assertEqual(response.status_code, 200)
        existing.refresh_from_db()
        self.assertTrue(existing.is_staff)
        self.assertTrue(existing.is_superuser)

"""An invitation speaks for the Admin who sent it: once they are no longer an active Admin it creates nobody."""

from apps.authn.models.members.admin_invitation import AdminInvitation
from apps.authn.tests.admin.invitations.test_invitation import Member, _AcceptInvitationViewCase


class InvitationSenderRemovedTests(_AcceptInvitationViewCase):
    def _post(self, invitation):
        return self.client.post(
            f"/authn/invite/{invitation.token}/",
            {
                "first_name": "New",
                "last_name": "Admin",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

    def _assert_refused(self, invitation):
        response = self.client.get(f"/authn/invite/{invitation.token}/")
        self.assertNotContains(response, "invite@example.com", status_code=response.status_code)
        self._post(invitation)
        self.assertFalse(Member.objects.filter(contact_emails__email_address="invite@example.com").exists())
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, AdminInvitation.Status.CANCELLED)
        self.assertFalse(invitation.is_valid)

    def test_a_demoted_sender_invites_nobody(self):
        invitation = self._create_invitation()
        sender = invitation.invited_by
        sender.is_staff = False
        sender.save(update_fields=["is_staff"])

        self._assert_refused(invitation)

    def test_a_deactivated_sender_invites_nobody(self):
        invitation = self._create_invitation()
        sender = invitation.invited_by
        sender.is_active = False
        sender.save(update_fields=["is_active"])

        self._assert_refused(invitation)

    def test_a_deleted_sender_invites_nobody(self):
        invitation = self._create_invitation()
        invitation.invited_by.delete()
        invitation.refresh_from_db()

        self._assert_refused(invitation)

    def test_an_invitation_without_a_sender_is_not_valid(self):
        invitation = self._create_invitation(invited_by=None)

        self._assert_refused(invitation)

    def test_a_sender_who_is_still_an_admin_keeps_the_invitation_valid(self):
        invitation = self._create_invitation()

        self.assertTrue(invitation.is_valid)

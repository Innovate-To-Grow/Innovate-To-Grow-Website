from django.test import override_settings
from django.utils import timezone

from apps.authn.models import AdminInvitation
from apps.authn.tests.admin.members.security.admins.fixtures import AdminPeersCase


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class InvitationTokenTests(AdminPeersCase):
    """An invitation link creates an Admin, so only the Admin who sent it sees it (to copy it when the email fails)."""

    def _invitation(self, sender):
        return AdminInvitation.objects.create(
            email="invitee@example.com",
            role=AdminInvitation.Role.ADMIN,
            token=AdminInvitation.generate_token(),
            status=AdminInvitation.Status.PENDING,
            expires_at=timezone.now() + timezone.timedelta(days=7),
            invited_by=sender,
        )

    def _page(self, invitation):
        response = self.client.get(f"/admin/authn/admininvitation/{invitation.pk}/change/")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_sending_admin_sees_the_link(self):
        invitation = self._invitation(self.admin)

        page = self._page(invitation)

        self.assertIn(f"/authn/invite/{invitation.token}/", page)

    def test_another_admin_does_not_see_the_link(self):
        invitation = self._invitation(self.other_admin)

        page = self._page(invitation)

        self.assertNotIn(invitation.token, page)
        self.assertIn("Shown only to the Admin who sent it.", page)

    def test_an_expired_link_is_not_shown_even_to_its_sender(self):
        invitation = self._invitation(self.admin)
        invitation.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        invitation.save(update_fields=["expires_at"])

        page = self._page(invitation)

        self.assertNotIn(invitation.token, page)
        self.assertIn("No longer valid.", page)

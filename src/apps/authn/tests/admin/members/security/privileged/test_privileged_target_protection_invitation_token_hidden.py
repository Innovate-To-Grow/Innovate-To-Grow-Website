from django.test import override_settings
from django.utils import timezone

from apps.authn.models import AdminInvitation
from apps.authn.tests.admin.members.security.privileged.test_privileged_target_protection import (
    _PrivilegedTargetProtectionCase,
)


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class PrivilegedTargetProtectionTests(_PrivilegedTargetProtectionCase):
    def test_invitation_token_hidden_from_view_only_staff(self):
        """The invitation token is a bearer credential for an is_staff account, so it renders only
        for superusers; view access itself stays."""
        invitation = AdminInvitation.objects.create(
            email="invitee@example.com",
            role=AdminInvitation.Role.ADMIN,
            token=AdminInvitation.generate_token(),
            status=AdminInvitation.Status.PENDING,
            expires_at=timezone.now() + timezone.timedelta(days=7),
            invited_by=self.master,
        )
        url = f"/admin/authn/admininvitation/{invitation.pk}/change/"

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(invitation.token, response.content.decode())

        self.client.force_login(self.master)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(invitation.token, response.content.decode())

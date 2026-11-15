from apps.authn.forms.invitation import AcceptInvitationForm
from apps.authn.models import ContactEmail
from apps.authn.models.members.admin_invitation import AdminInvitation
from apps.authn.tests.admin.invitations.test_invitation import Member, _AcceptInvitationViewCase


class AcceptInvitationViewTests(_AcceptInvitationViewCase):
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
        self.assertEqual(existing.admin_apps, [])

    def test_post_existing_inactive_verified_member_upgrades_and_activates(self):
        existing = Member.objects.create_user(
            password="StrongPass123!",
            is_active=False,
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
        self.assertTrue(existing.is_active)

    def test_post_claims_existing_unclaimed_contact_email(self):
        ContactEmail.objects.create(
            member=None,
            email_address="invite@example.com",
            email_type="other",
            subscribe=False,
            verified=False,
        )
        invitation = self._create_invitation(email="invite@example.com")

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
        self.assertEqual(ContactEmail.objects.filter(email_address="invite@example.com").count(), 1)
        contact = ContactEmail.objects.get(email_address="invite@example.com")
        self.assertEqual(contact.email_type, "primary")
        self.assertTrue(contact.verified)
        self.assertFalse(contact.subscribe)
        self.assertTrue(contact.member.is_staff)

    def test_post_refuses_to_steal_a_contact_email_owned_by_another_member(self):
        """Moving a ContactEmail between accounts is an account-takeover primitive.

        The address is a sign-in factor, so re-pointing an existing row at the invitee handed them
        the other member's recovery address. Refuse and report it instead.
        """
        other = Member.objects.create_user(password="StrongPass123!", is_active=True, is_staff=False)
        ContactEmail.objects.create(
            member=other,
            email_address="invite@example.com",
            email_type="secondary",
            verified=False,
        )
        invitation = self._create_invitation(email="invite@example.com")

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
        self.assertContains(response, "already belongs to another member")
        other.refresh_from_db()
        self.assertFalse(other.is_staff)
        contact = ContactEmail.objects.get(email_address="invite@example.com")
        self.assertEqual(contact.member_id, other.id)
        self.assertEqual(contact.email_type, "secondary")
        self.assertFalse(contact.verified)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, AdminInvitation.Status.PENDING)

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

    def test_name_fields_reject_lone_markup_delimiters(self):
        form = AcceptInvitationForm(
            data={
                "email": "invite@example.com",
                "first_name": "Less < Than",
                "last_name": "Greater > Than",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("HTML tags are not allowed.", form.errors["first_name"])
        self.assertIn("HTML tags are not allowed.", form.errors["last_name"])

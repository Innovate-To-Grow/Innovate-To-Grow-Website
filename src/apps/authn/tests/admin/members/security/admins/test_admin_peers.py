"""Every Admin may manage every member, another Admin's password and contact records included."""

from django.test import override_settings

from apps.authn.models import ContactEmail
from apps.authn.tests.admin.members.security.admins.fixtures import AdminPeersCase


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class AdminPeerPasswordTests(AdminPeersCase):
    def assert_password_changed(self, target, new_password):
        old_hash = target.password

        response = self.client.post(self.password_url(target), {"password1": new_password, "password2": new_password})

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertNotEqual(target.password, old_hash)
        self.assertTrue(target.check_password(new_password))

    def test_an_admin_can_open_another_admins_password_page(self):
        self.assertEqual(self.client.get(self.password_url(self.other_admin)).status_code, 200)

    def test_an_admin_can_set_another_admins_password(self):
        self.assert_password_changed(self.other_admin, "Rotated!12345")

    def test_an_admin_can_set_a_regular_members_password(self):
        self.assert_password_changed(self.regular, "BrandNew!12345")

    def test_an_admin_can_set_their_own_password(self):
        self.assert_password_changed(self.admin, "MyOwnNew!12345")


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class AdminPeerContactTests(AdminPeersCase):
    def test_an_admin_can_attach_a_verified_email_to_another_admin(self):
        response = self.client.post(
            "/admin/authn/contactemail/add/",
            {
                "member": str(self.other_admin.pk),
                "email_address": "otto.alt@example.test",
                "email_type": "secondary",
                "verified": "on",
                "subscribe": "on",
                "_save": "1",
            },
        )

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        row = ContactEmail.objects.get(email_address="otto.alt@example.test")
        self.assertEqual((row.member_id, row.verified), (self.other_admin.pk, True))

    def test_another_admins_contact_email_page_is_editable(self):
        row = ContactEmail.objects.create(
            member=self.other_admin, email_address="otto.alt2@example.com", email_type="secondary", verified=False
        )

        response = self.client.get(f"/admin/authn/contactemail/{row.pk}/change/")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('name="_save"', content)
        self.assertIn('name="verified"', content)

    def test_an_admin_can_change_another_admins_contact_email(self):
        row = ContactEmail.objects.create(
            member=self.other_admin, email_address="otto.alt3@example.com", email_type="secondary", verified=False
        )

        response = self.client.post(
            f"/admin/authn/contactemail/{row.pk}/change/",
            {
                "member": str(self.other_admin.pk),
                "email_address": "otto.alt3@example.com",
                "email_type": "secondary",
                "verified": "on",
                "_save": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertTrue(row.verified)

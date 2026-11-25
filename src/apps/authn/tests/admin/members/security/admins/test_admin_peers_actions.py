"""The bulk actions, the delete paths and phone normalization treat another Admin's records like anyone else's."""

from django.contrib import admin
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.tests.admin.members.security.admins.fixtures import AdminPeersCase


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class AdminPeerActionTests(AdminPeersCase):
    def test_mark_verified_covers_another_admins_email(self):
        admin_row = ContactEmail.objects.create(
            member=self.other_admin, email_address="otto.alt@example.com", email_type="secondary", verified=False
        )
        regular_row = ContactEmail.objects.create(
            member=self.regular, email_address="reg.alt@example.com", email_type="secondary", verified=False
        )

        self.client.post(
            "/admin/authn/contactemail/",
            {"action": "mark_verified", "_selected_action": [str(admin_row.pk), str(regular_row.pk)], "index": "0"},
        )

        self.assertEqual(ContactEmail.objects.filter(pk__in=[admin_row.pk, regular_row.pk], verified=True).count(), 2)

    def test_make_primary_works_on_another_admins_email(self):
        secondary = ContactEmail.objects.create(
            member=self.other_admin, email_address="otto.new@example.com", email_type="secondary", verified=True
        )

        response = self.client.post(
            "/admin/authn/contactemail/",
            {"action": "make_primary", "_selected_action": [str(secondary.pk)], "index": "0"},
        )

        self.assertEqual(response.status_code, 302)
        secondary.refresh_from_db()
        self.assertEqual(secondary.email_type, "primary")

    def test_an_admin_can_deactivate_another_admin_and_a_member_together(self):
        self.changelist_action("deactivate_members", [self.other_admin, self.regular])

        self.assertFalse(Member.objects.filter(pk__in=[self.other_admin.pk, self.regular.pk], is_active=True).exists())

    def test_another_admins_flags_are_editable(self):
        model_admin = admin.site._registry[Member]
        request = RequestFactory().get("/")
        request.user = self.admin

        readonly = model_admin.get_readonly_fields(request, self.other_admin)

        self.assertNotIn("is_active", readonly)
        self.assertNotIn("is_staff", readonly)
        self.assertTrue(model_admin.has_delete_permission(request, self.other_admin))

    def drop_primary_email(self, member):
        # Deleting a member whose primary email is on file is refused by the admin's related-object check
        # (``ContactEmailAdmin.has_delete_permission``), whoever the member is, so these tests use a member without one.
        ContactEmail.objects.filter(member=member).delete()

    def test_an_admin_can_delete_another_admin_on_the_delete_page(self):
        self.drop_primary_email(self.other_admin)
        response = self.client.post(f"/admin/authn/member/{self.other_admin.pk}/delete/", {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Member.objects.filter(pk=self.other_admin.pk).exists())

    def test_an_admin_can_delete_another_admin_and_a_member_in_bulk(self):
        self.drop_primary_email(self.other_admin)
        response = self.changelist_action("delete_selected", [self.other_admin, self.regular], post="yes")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Member.objects.filter(pk__in=[self.other_admin.pk, self.regular.pk]).exists())

    def test_the_bulk_delete_shows_its_confirmation_page_first(self):
        response = self.changelist_action("delete_selected", [self.regular])

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Member.objects.filter(pk=self.regular.pk).exists())

    def test_phone_normalization_rewrites_every_owners_numbers(self):
        # bulk_create bypasses the model's save-time normalization, so both rows need fixing.
        ContactPhone.objects.bulk_create(
            [
                ContactPhone(member=self.other_admin, phone_number="+12095551111", region="1-US"),
                ContactPhone(member=self.regular, phone_number="+12095552222", region="1-US"),
            ]
        )

        response = self.client.post(reverse("admin:authn_contactphone_normalize_apply"), {})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactPhone.objects.get(member=self.other_admin).phone_number, "2095551111")
        self.assertEqual(ContactPhone.objects.get(member=self.regular).phone_number, "2095552222")

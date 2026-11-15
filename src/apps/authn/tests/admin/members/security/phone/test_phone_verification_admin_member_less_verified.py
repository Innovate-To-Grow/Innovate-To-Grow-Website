from django.contrib import admin
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.authn.admin.members.contact.phone import ContactPhoneAdmin
from apps.authn.models import ContactPhone, Member
from apps.authn.tests.admin.members.security.phone.test_phone_verification_admin import (
    AdminPhoneTestCase,
    _change_url,
    _last_change_message,
    _verify_url,
)
from apps.core.admin.confirmation.pending import SESSION_KEY_PREFIX


class ContactPhoneVerifiedFieldTests(AdminPhoneTestCase):
    def test_a_member_less_verified_number_attached_to_a_member_starts_unverified(self):
        ContactPhone.objects.filter(pk=self.phone.pk).update(member=None, verified=True)
        self.phone.refresh_from_db()

        self.assertEqual(self.post_phone(self.phone, verified=True, member=str(self.member.pk)).status_code, 302)

        self.phone.refresh_from_db()
        self.assertEqual((self.phone.member_id, self.phone.verified), (self.member.pk, False))

    def test_the_history_names_the_unverify_of_a_move(self):
        self.mark_verified(self.phone)
        other = Member.objects.create_user(password=None, first_name="New", last_name="Owner", is_active=True)

        self.post_phone(self.phone, verified=True, member=str(other.pk))

        self.assertEqual(_last_change_message(self.phone), "Changed Member and Verified.")

    def test_the_history_names_the_unverify_of_a_changed_number(self):
        self.mark_verified(self.phone)

        self.post_phone(self.phone, verified=True, phone_number="2095550199")

        self.assertEqual(_last_change_message(self.phone), "Changed Phone number and Verified.")

    def test_moving_an_unverified_number_changes_only_its_member(self):
        other = Member.objects.create_user(password=None, first_name="New", last_name="Owner", is_active=True)

        self.post_phone(self.phone, verified=False, member=str(other.pk))

        self.assertEqual(_last_change_message(self.phone), "Changed Member.")

    def test_an_unrelated_save_leaves_the_number_verified(self):
        self.mark_verified(self.phone)

        self.post_phone(self.phone, verified=True, subscribe="on")

        self.phone.refresh_from_db()
        self.assertEqual((self.phone.member_id, self.phone.verified), (self.member.pk, True))
        self.assertEqual(_last_change_message(self.phone), "Changed Subscribed.")

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_the_typed_confirmation_lists_the_unverify_of_a_move(self):
        self.mark_verified(self.phone)
        self.keep_a_way_to_sign_in(self.member)
        other = Member.objects.create_user(password=None, first_name="New", last_name="Owner", is_active=True)

        self.post_phone(self.phone, verified=True, member=str(other.pk))

        pending = self.client.session[f"{SESSION_KEY_PREFIX}_authn_contactphone"]
        rows = {row["field"]: (row["old_value"], row["new_value"]) for row in pending["diff"]}
        self.assertEqual(sorted(rows), ["member", "verified"])
        self.assertEqual(rows["verified"], ("Yes", "No"))
        self.phone.refresh_from_db()
        self.assertEqual((self.phone.member_id, self.phone.verified), (self.member.pk, True))  # Not saved yet.

    def test_saving_backstops_a_move_the_form_left_verified(self):
        # As if ``verified`` were not a form field: the save itself drops a verification the new member never proved.
        self.mark_verified(self.phone)
        self.keep_a_way_to_sign_in(self.member)
        other = Member.objects.create_user(password=None, first_name="New", last_name="Owner", is_active=True)
        request = RequestFactory().post("/")
        request.user = self.admin
        moved = ContactPhone.objects.get(pk=self.phone.pk)
        moved.member = other

        ContactPhoneAdmin(ContactPhone, admin.site).save_model(request, moved, form=None, change=True)

        self.phone.refresh_from_db()
        self.assertEqual((self.phone.member_id, self.phone.verified), (other.pk, False))

    def test_saving_an_unmoved_verified_number_keeps_it_verified(self):
        self.mark_verified(self.phone)
        request = RequestFactory().post("/")
        request.user = self.admin

        ContactPhoneAdmin(ContactPhone, admin.site).save_model(request, self.phone, form=None, change=True)

        self.phone.refresh_from_db()
        self.assertTrue(self.phone.verified)

    def test_a_phone_added_here_starts_unverified(self):
        response = self.client.post(
            reverse("admin:authn_contactphone_add"),
            {"member": str(self.member.pk), "phone_number": "2095550122", "region": "1-US", "verified": "on"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ContactPhone.objects.get(phone_number="2095550122").verified)

    def test_the_list_shows_a_badge_and_no_verified_checkbox(self):
        other = Member.objects.create_user(password=None, is_active=True)
        ContactPhone.objects.create(member=other, phone_number="2095550133", region="1-US", verified=True)

        response = self.client.get(reverse("admin:authn_contactphone_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unverified")
        self.assertContains(response, "Verified")
        self.assertNotContains(response, 'name="form-0-verified"')
        self.assertContains(response, 'name="form-0-subscribe"')
        self.assertNotIn("mark_verified", dict(response.context["action_form"].fields["action"].choices))

    def test_the_change_page_links_an_unverified_number_to_the_staff_check(self):
        response = self.client.get(_change_url(self.phone))

        self.assertContains(response, "Unverified · no SMS sign-in")
        self.assertContains(response, _verify_url(self.phone))

        self.mark_verified(self.phone)
        response = self.client.get(_change_url(self.phone))
        self.assertContains(response, "Verified · SMS sign-in on")
        self.assertNotContains(response, _verify_url(self.phone))

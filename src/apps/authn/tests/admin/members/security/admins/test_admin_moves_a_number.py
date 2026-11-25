from django.urls import reverse

from apps.authn.models import Member
from apps.authn.tests.admin.members.security.phone.test_phone_verification_admin import (
    AdminPhoneTestCase,
    _form_fields,
    _last_change_message,
    _verify_url,
)


class AdminMovesANumberTests(AdminPhoneTestCase):
    """The reported path, by an Admin made with ``is_staff`` only (not ``create_superuser``)."""

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        self.staffer = Member.objects.create_user(password=None, first_name="Staff", last_name="Er", is_active=True)
        self.staffer.is_staff = True
        self.staffer.save(update_fields=["is_staff"])
        self.client.force_login(self.staffer)

    def test_a_verified_number_moved_between_two_members_starts_unverified(self):
        self.mark_verified(self.phone)
        other = Member.objects.create_user(password=None, first_name="New", last_name="Owner", is_active=True)

        response = self.post_phone(self.phone, verified=True, member=str(other.pk))

        self.assertEqual(response.status_code, 302)
        self.phone.refresh_from_db()
        self.assertEqual((self.phone.member_id, self.phone.verified), (other.pk, False))
        self.assertEqual(_last_change_message(self.phone), "Changed Member and Verified.")


class MemberPageTests(AdminPhoneTestCase):
    def post_member(self, **phone_fields):
        url = reverse("admin:authn_member_change", args=[self.member.pk])
        data = _form_fields(self.client.get(url).content.decode())
        data.update({f"contact_phones-0-{key}": value for key, value in phone_fields.items()})
        if phone_fields.get("verified") is None:
            data.pop("contact_phones-0-verified", None)
        return self.client.post(url, data)

    def test_ticking_verified_in_the_inline_changes_nothing(self):
        response = self.post_member(verified="on")

        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.phone.refresh_from_db()
        self.assertFalse(self.phone.verified)

    def test_a_number_changed_in_the_inline_starts_unverified(self):
        self.mark_verified(self.phone)

        response = self.post_member(verified="on", phone_number="2095550144")

        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.phone.refresh_from_db()
        self.assertEqual((self.phone.phone_number, self.phone.verified), ("2095550144", False))

    def test_saving_the_member_page_keeps_a_verified_number_verified(self):
        # The inline's member is the page's own member: saving it moves nothing.
        self.mark_verified(self.phone)

        response = self.post_member(verified="on")

        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.phone.refresh_from_db()
        self.assertEqual((self.phone.member_id, self.phone.verified), (self.member.pk, True))

    def test_changing_another_field_in_the_inline_keeps_a_verified_number_verified(self):
        # The row is saved this time (Subscribed changed), so its member must still compare as unchanged: the inline
        # gets its member's pk as a string, the stored phone a UUID.
        self.mark_verified(self.phone)

        response = self.post_member(verified="on", subscribe="on")

        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.phone.refresh_from_db()
        self.assertEqual(
            (self.phone.member_id, self.phone.verified, self.phone.subscribe), (self.member.pk, True, True)
        )

    def test_unticking_in_the_inline_stops_sms_sign_in(self):
        self.mark_verified(self.phone)

        self.assertEqual(self.post_member(verified=None).status_code, 302)

        self.phone.refresh_from_db()
        self.assertFalse(self.phone.verified)

    def test_the_inline_shows_the_state_and_the_staff_check(self):
        response = self.client.get(reverse("admin:authn_member_change", args=[self.member.pk]))

        self.assertContains(response, "Unverified · no SMS sign-in")
        self.assertContains(response, _verify_url(self.phone))

    def test_the_member_list_flags_an_unverified_primary_phone(self):
        response = self.client.get(reverse("admin:authn_member_changelist"))

        self.assertContains(response, "+12095550111 (unverified)")

        self.mark_verified(self.phone)
        response = self.client.get(reverse("admin:authn_member_changelist"))
        self.assertContains(response, "+12095550111")
        self.assertNotContains(response, "(unverified)")

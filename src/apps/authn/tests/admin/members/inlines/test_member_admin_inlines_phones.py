from django.test import override_settings

from apps.authn.models import ContactPhone
from apps.authn.tests.admin.members.inlines.test_member_admin_inlines import _MemberAdminInlineUUIDSubmitCase

from .inline_helpers import Member


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class MemberAdminInlineUUIDSubmitTest(_MemberAdminInlineUUIDSubmitCase):
    def test_add_contact_phone_with_none_id_does_not_crash(self):
        """Adding a new phone inline row must tolerate id='None'."""
        self.client.force_login(self.admin)
        data = self._build_post_data(
            {
                "contact_phones-TOTAL_FORMS": "1",
                "contact_phones-INITIAL_FORMS": "0",
                "contact_phones-0-id": "None",
                "contact_phones-0-member": "None",
                "contact_phones-0-phone_number": "+1 (209) 576-5113",
                "contact_phones-0-region": "1-US",
                "contact_phones-0-verified": "on",
                "contact_phones-0-subscribe": "on",
            }
        )

        resp = self.client.post(self._change_url(), data)
        content = resp.content.decode() if resp.status_code == 200 else ""

        self.assertNotIn("is not a valid UUID", content)
        self.assertEqual(resp.status_code, 302, content)
        phone = ContactPhone.objects.get(member=self.target, phone_number="2095765113")
        self.assertEqual(phone.region, "1-US")
        # A phone added by staff starts unverified whatever is posted: only an SMS code verifies a number.
        self.assertFalse(phone.verified)

    def test_change_member_rejects_contact_phone_owned_by_other_member(self):
        """Admin inline must not move another member's phone onto this member."""
        other = Member.objects.create_user(
            password="other123",
            first_name="Other",
            last_name="User",
            is_active=True,
        )
        ContactPhone.objects.create(
            member=other,
            phone_number="2095765114",
            region="1-US",
            verified=True,
        )
        self.client.force_login(self.admin)
        data = self._build_post_data(
            {
                "contact_phones-TOTAL_FORMS": "1",
                "contact_phones-INITIAL_FORMS": "0",
                "contact_phones-0-id": "None",
                "contact_phones-0-member": "None",
                "contact_phones-0-phone_number": "+1 (209) 576-5114",
                "contact_phones-0-region": "1-US",
                "contact_phones-0-verified": "on",
                "contact_phones-0-subscribe": "on",
            }
        )

        resp = self.client.post(self._change_url(), data)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "This phone number is already assigned to another member.")
        self.assertFalse(ContactPhone.objects.filter(member=self.target, phone_number="2095765114").exists())

    def test_add_member_rejects_contact_phone_owned_by_other_member(self):
        """Admin add page must reject a new member with another member's phone."""
        other = Member.objects.create_user(
            password="other123",
            first_name="Other",
            last_name="User",
            is_active=True,
        )
        ContactPhone.objects.create(
            member=other,
            phone_number="2095765115",
            region="1-US",
            verified=True,
        )
        self.client.force_login(self.admin)
        data = {
            "password1": "",
            "password2": "",
            "first_name": "Monique",
            "middle_name": "",
            "last_name": "Hampton",
            "organization": "",
            "title": "",
            "is_active": "on",
            "contact_emails-TOTAL_FORMS": "0",
            "contact_emails-INITIAL_FORMS": "0",
            "contact_emails-MIN_NUM_FORMS": "0",
            "contact_emails-MAX_NUM_FORMS": "1000",
            "contact_phones-TOTAL_FORMS": "1",
            "contact_phones-INITIAL_FORMS": "0",
            "contact_phones-MIN_NUM_FORMS": "0",
            "contact_phones-MAX_NUM_FORMS": "1000",
            "contact_phones-0-id": "None",
            "contact_phones-0-member": "None",
            "contact_phones-0-phone_number": "+1 (209) 576-5115",
            "contact_phones-0-region": "1-US",
            "contact_phones-0-verified": "on",
            "contact_phones-0-subscribe": "on",
            "_save": "Save",
        }

        resp = self.client.post("/admin/authn/member/add/", data)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "This phone number is already assigned to another member.")
        self.assertFalse(Member.objects.filter(first_name="Monique", last_name="Hampton").exists())
        self.assertEqual(ContactPhone.objects.filter(phone_number="2095765115").count(), 1)

    def test_add_member_with_contact_phone_normalizes_number(self):
        """Admin add page should store phone inline input as national digits."""
        self.client.force_login(self.admin)
        data = {
            "password1": "",
            "password2": "",
            "first_name": "Phone",
            "middle_name": "",
            "last_name": "User",
            "organization": "",
            "title": "",
            "is_active": "on",
            "contact_emails-TOTAL_FORMS": "0",
            "contact_emails-INITIAL_FORMS": "0",
            "contact_emails-MIN_NUM_FORMS": "0",
            "contact_emails-MAX_NUM_FORMS": "1000",
            "contact_phones-TOTAL_FORMS": "1",
            "contact_phones-INITIAL_FORMS": "0",
            "contact_phones-MIN_NUM_FORMS": "0",
            "contact_phones-MAX_NUM_FORMS": "1000",
            "contact_phones-0-id": "None",
            "contact_phones-0-member": "None",
            "contact_phones-0-phone_number": "+1 (209) 576-5116",
            "contact_phones-0-region": "1-US",
            "contact_phones-0-verified": "on",
            "contact_phones-0-subscribe": "on",
            "_save": "Save",
        }

        resp = self.client.post("/admin/authn/member/add/", data)

        self.assertEqual(resp.status_code, 302)
        phone = ContactPhone.objects.get(phone_number="2095765116")
        self.assertEqual(phone.member.first_name, "Phone")
        self.assertEqual(phone.member.last_name, "User")

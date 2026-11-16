from django.contrib import admin
from django.test import override_settings

from apps.authn.admin.members.forms import MemberCreationForm
from apps.authn.models import ContactEmail
from apps.authn.tests.admin.members.inlines.test_member_admin_inlines import _MemberAdminInlineUUIDSubmitCase

from .inline_helpers import Member


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class MemberAdminInlineUUIDSubmitTest(_MemberAdminInlineUUIDSubmitCase):
    def test_add_member_with_contact_email_none_id_creates_member(self):
        """Adding a member with a new email inline must tolerate id='None'."""
        self.client.force_login(self.admin)
        email = "admin-add-inline@example.com"
        data = {
            "password1": "",
            "password2": "",
            "first_name": "Monique",
            "middle_name": "",
            "last_name": "Hampton",
            "organization": "",
            "title": "",
            "is_active": "on",
            "contact_emails-TOTAL_FORMS": "1",
            "contact_emails-INITIAL_FORMS": "0",
            "contact_emails-MIN_NUM_FORMS": "0",
            "contact_emails-MAX_NUM_FORMS": "1000",
            "contact_emails-0-id": "None",
            "contact_emails-0-member": "None",
            "contact_emails-0-email_address": email,
            "contact_emails-0-email_type": "primary",
            "contact_emails-0-verified": "on",
            "contact_emails-0-subscribe": "on",
            "contact_phones-TOTAL_FORMS": "0",
            "contact_phones-INITIAL_FORMS": "0",
            "contact_phones-MIN_NUM_FORMS": "0",
            "contact_phones-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }

        resp = self.client.post("/admin/authn/member/add/", data)
        content = resp.content.decode() if resp.status_code == 200 else ""

        self.assertNotIn("is not a valid UUID", content)
        self.assertEqual(resp.status_code, 302)
        contact = ContactEmail.objects.get(email_address=email)
        self.assertEqual(contact.email_type, "primary")
        self.assertTrue(contact.verified)
        self.assertEqual(contact.member.first_name, "Monique")
        self.assertEqual(contact.member.last_name, "Hampton")

    def test_save_new_member_with_none_string_id_generates_uuid(self):
        """Admin save must tolerate third-party widgets assigning id='None'."""
        member_admin = admin.site._registry[Member]
        member = Member(first_name="None", last_name="Id", is_active=True)
        member.id = "None"

        member_admin.save_model(request=None, obj=member, form=None, change=False)

        saved = Member.objects.get(pk=member.pk)
        self.assertEqual(saved.first_name, "None")
        self.assertNotEqual(str(saved.pk), "None")

    def test_save_form_assigns_uuid_before_inline_formsets(self):
        """Admin add must assign a UUID before Django validates inline rows."""
        member_admin = admin.site._registry[Member]
        form = MemberCreationForm(data={"password1": "", "password2": ""})
        self.assertTrue(form.is_valid(), form.errors)

        member = member_admin.save_form(request=None, form=form, change=False)

        self.assertIsNotNone(member.pk)
        self.assertNotEqual(str(member.pk), "None")

    def test_change_member_rejects_contact_email_owned_by_other_member(self):
        """Admin inline must not move another member's email onto this member."""
        other = Member.objects.create_user(
            password="other123",
            first_name="Other",
            last_name="User",
            is_active=True,
        )
        ContactEmail.objects.create(
            member=other,
            email_address="claimed@example.com",
            email_type="primary",
            verified=True,
        )
        self.client.force_login(self.admin)
        data = self._build_post_data(
            {
                "contact_emails-TOTAL_FORMS": "1",
                "contact_emails-INITIAL_FORMS": "0",
                "contact_emails-0-id": "None",
                "contact_emails-0-member": "None",
                "contact_emails-0-email_address": "CLAIMED@example.com",
                "contact_emails-0-email_type": "primary",
                "contact_emails-0-verified": "on",
                "contact_emails-0-subscribe": "on",
            }
        )

        resp = self.client.post(self._change_url(), data)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "This email address is already assigned to another member.")
        self.assertFalse(
            ContactEmail.objects.filter(member=self.target, email_address__iexact="claimed@example.com").exists()
        )

    def test_add_member_rejects_contact_email_owned_by_other_member(self):
        """Admin add page must reject a new member with another member's email."""
        other = Member.objects.create_user(
            password="other123",
            first_name="Other",
            last_name="User",
            is_active=True,
        )
        ContactEmail.objects.create(
            member=other,
            email_address="claimed-add@example.com",
            email_type="primary",
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
            "contact_emails-TOTAL_FORMS": "1",
            "contact_emails-INITIAL_FORMS": "0",
            "contact_emails-MIN_NUM_FORMS": "0",
            "contact_emails-MAX_NUM_FORMS": "1000",
            "contact_emails-0-id": "None",
            "contact_emails-0-member": "None",
            "contact_emails-0-email_address": "CLAIMED-ADD@example.com",
            "contact_emails-0-email_type": "primary",
            "contact_emails-0-verified": "on",
            "contact_emails-0-subscribe": "on",
            "contact_phones-TOTAL_FORMS": "0",
            "contact_phones-INITIAL_FORMS": "0",
            "contact_phones-MIN_NUM_FORMS": "0",
            "contact_phones-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }

        resp = self.client.post("/admin/authn/member/add/", data)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "This email address is already assigned to another member.")
        self.assertFalse(Member.objects.filter(first_name="Monique", last_name="Hampton").exists())
        self.assertEqual(ContactEmail.objects.filter(email_address__iexact="claimed-add@example.com").count(), 1)

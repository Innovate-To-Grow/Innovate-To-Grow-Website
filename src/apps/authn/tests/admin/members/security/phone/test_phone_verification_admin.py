"""Phone verification in the admin: a number becomes verified only with an SMS code, never with a tick.

A verified number signs in to its account with a texted code, so staff may switch verification off but not on; a
number whose digits change, or that moves to another member, starts unverified; the state is shown as a badge; and the
staff path for a member who cannot sign in another way is **Verify by SMS code** (send a code, the member reads it
back, staff enter it).
"""

from html.parser import HTMLParser

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.tests.helpers.sms_provider import SMS_CODE, patch_sms_provider

NUMBER = "2095550111"


def _last_change_message(phone) -> str:
    return LogEntry.objects.filter(object_id=str(phone.pk)).latest("action_time").get_change_message()


def _change_url(phone):
    return reverse("admin:authn_contactphone_change", args=[phone.pk])


def _verify_url(phone):
    return reverse("admin:authn_contactphone_verify_by_code", args=[phone.pk])


def _form_fields(html: str) -> dict[str, str]:
    """Every submittable value on an admin page, the way a browser would post the form unchanged."""
    fields: dict[str, str] = {}
    state = {"select": None, "textarea": None}

    class _Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attr = dict(attrs)
            name = attr.get("name")
            if tag == "input" and name and "disabled" not in attr:
                if attr.get("type") != "checkbox" or "checked" in attr:
                    fields.setdefault(name, attr.get("value", "on" if attr.get("type") == "checkbox" else ""))
            elif tag in ("select", "textarea") and name:
                state[tag] = name
            elif tag == "option" and state["select"] and "selected" in attr:
                fields.setdefault(state["select"], attr.get("value", ""))

        def handle_data(self, data):
            if state["textarea"]:
                fields.setdefault(state["textarea"], data.strip())

        def handle_endtag(self, tag):
            if tag in ("select", "textarea"):
                state[tag] = None

    _Parser().feed(html)
    fields.pop("_addanother", None)
    fields.pop("_continue", None)
    fields["_save"] = "Save"
    return fields


class AdminPhoneTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.admin = Member.objects.create_superuser(
            password="StrongPass123!", first_name="Ad", last_name="Min", is_active=True
        )
        self.member = Member.objects.create_user(password=None, first_name="Mem", last_name="Ber", is_active=True)
        self.phone = ContactPhone.objects.create(member=self.member, phone_number=NUMBER, region="1-US")
        self.client.force_login(self.admin)

    def post_phone(self, phone, *, verified, **overrides):
        data = {
            "member": str(phone.member_id),
            "phone_number": phone.phone_number,
            "region": phone.region,
            "_save": "Save",
            **({"verified": "on"} if verified else {}),
            **overrides,
        }
        return self.client.post(_change_url(phone), data)

    def mark_verified(self, phone):
        ContactPhone.objects.filter(pk=phone.pk).update(verified=True)
        phone.refresh_from_db()

    def keep_a_way_to_sign_in(self, member):
        """Give ``member`` a verified email, so moving their number away leaves them able to sign in: the test then
        sees only the move itself, not what the admin says about a member who can no longer sign in."""
        ContactEmail.objects.create(
            member=member, email_address="mem.ber@example.com", email_type="primary", verified=True
        )


class ContactPhoneVerifiedFieldTests(AdminPhoneTestCase):
    def test_ticking_verified_on_an_unverified_number_changes_nothing(self):
        response = self.post_phone(self.phone, verified=True)

        self.assertEqual(response.status_code, 302)
        self.phone.refresh_from_db()
        self.assertFalse(self.phone.verified)

    def test_the_verified_box_can_only_be_unticked(self):
        unverified = self.client.get(_change_url(self.phone)).context["adminform"].form.fields["verified"]
        self.mark_verified(self.phone)
        verified = self.client.get(_change_url(self.phone)).context["adminform"].form.fields["verified"]

        self.assertEqual((unverified.disabled, verified.disabled), (True, False))
        self.assertIn("becomes verified only with an SMS code", verified.help_text)

    def test_unticking_stops_sms_sign_in(self):
        self.mark_verified(self.phone)

        self.assertEqual(self.post_phone(self.phone, verified=False).status_code, 302)

        self.phone.refresh_from_db()
        self.assertFalse(self.phone.verified)

    def test_a_changed_number_starts_unverified(self):
        self.mark_verified(self.phone)

        response = self.post_phone(self.phone, verified=True, phone_number="(209) 555-0199")

        self.assertEqual(response.status_code, 302)
        self.phone.refresh_from_db()
        self.assertEqual((self.phone.phone_number, self.phone.verified), ("2095550199", False))

    def test_the_same_number_written_differently_stays_verified(self):
        self.mark_verified(self.phone)

        self.assertEqual(self.post_phone(self.phone, verified=True, phone_number="+1 (209) 555-0111").status_code, 302)

        self.phone.refresh_from_db()
        self.assertEqual((self.phone.phone_number, self.phone.verified), (NUMBER, True))

    def test_a_verified_number_moved_to_another_member_starts_unverified(self):
        # Its code proved that someone holds the phone, not that the new member does.
        self.mark_verified(self.phone)
        other = Member.objects.create_user(password=None, first_name="New", last_name="Owner", is_active=True)

        response = self.post_phone(self.phone, verified=True, member=str(other.pk))

        self.assertEqual(response.status_code, 302)
        self.phone.refresh_from_db()
        self.assertEqual((self.phone.member_id, self.phone.verified), (other.pk, False))

    def test_a_verified_number_unlinked_from_its_member_starts_unverified(self):
        self.mark_verified(self.phone)

        self.assertEqual(self.post_phone(self.phone, verified=True, member="").status_code, 302)

        self.phone.refresh_from_db()
        self.assertEqual((self.phone.member_id, self.phone.verified), (None, False))

    def test_the_holder_of_a_moved_number_cannot_sign_in_to_the_new_members_account(self):
        publish = patch_sms_provider(self)
        self.mark_verified(self.phone)
        other = Member.objects.create_user(password=None, first_name="New", last_name="Owner", is_active=True)
        self.assertEqual(self.post_phone(self.phone, verified=True, member=str(other.pk)).status_code, 302)

        api = APIClient()
        requested = api.post("/authn/phone-auth/request-code/", {"phone_number": NUMBER}, format="json")
        signed_in = api.post(
            "/authn/phone-auth/verify-code/",
            {"phone_number": NUMBER, "challenge_id": requested.data["challenge_id"], "code": SMS_CODE},
            format="json",
        )

        # A withheld code: answered like a send, nothing texted, and no code signs in to the new member's account.
        self.assertEqual(requested.status_code, 202)
        publish.assert_not_called()
        self.assertEqual(signed_in.status_code, 400)
        self.assertNotIn("access", signed_in.data)

"""Phone verification in the admin: a number becomes verified only with an SMS code, never with a tick.

A verified number signs in to its account with a texted code, so staff may switch verification off but not on; a
number whose digits change, or that moves to another member, starts unverified; the state is shown as a badge; and the
staff path for a member who cannot sign in another way is **Verify by SMS code** (send a code, the member reads it
back, staff enter it).
"""

from html.parser import HTMLParser

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.authn.admin.members.contact.phone import ContactPhoneAdmin
from apps.authn.admin.members.contact.phone_verification import same_member, sms_sign_in_status
from apps.authn.models import ContactPhone, Member, PhoneVerificationChallenge
from apps.authn.services.sms import PhoneVerificationDeliveryError
from apps.authn.tests.sms_provider import SMS_CODE, WRONG_CODE, patch_sms_provider
from apps.core.admin.mixins.confirm_on_save import SESSION_KEY_PREFIX

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


class AuthnStaffMoveTests(AdminPhoneTestCase):
    """The reported path: a staffer who is not the I2G Master, with only the Members (authn) grant."""

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        self.staffer = Member.objects.create_user(password=None, first_name="Staff", last_name="Er", is_active=True)
        self.staffer.is_staff = True
        self.staffer.admin_apps = ["authn"]
        self.staffer.save(update_fields=["is_staff", "admin_apps"])
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


class StaffVerifyByCodeTests(AdminPhoneTestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        self.publish = patch_sms_provider(self)

    def send(self):
        return self.client.post(_verify_url(self.phone), {"action": "send"}, follow=True)

    def enter(self, code):
        return self.client.post(_verify_url(self.phone), {"action": "verify", "code": code}, follow=True)

    @staticmethod
    def texts(response):
        return [str(message) for message in response.context["messages"]]

    def test_the_page_explains_the_check(self):
        response = self.client.get(_verify_url(self.phone))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ask the member to read the code to you")
        self.assertContains(response, 'value="send"')
        self.assertContains(response, 'name="code"')

    def test_the_code_the_member_reads_back_verifies_the_number(self):
        sent = self.send()

        self.assertIn("Code sent to (209)555-0111. Ask the member to read it to you", self.texts(sent)[0])
        self.assertEqual([call.kwargs["phone_number"] for call in self.publish.call_args_list], ["+12095550111"])
        challenge = PhoneVerificationChallenge.objects.get()
        self.assertEqual(
            (challenge.purpose, challenge.member_id, challenge.context_identifier),
            ("contact_phone_verify", self.member.pk, str(self.phone.pk)),
        )

        verified = self.enter(SMS_CODE)

        self.assertEqual(verified.redirect_chain[-1][0], _change_url(self.phone))
        self.assertIn("Verified. This number can now be used to sign in", self.texts(verified)[0])
        self.phone.refresh_from_db()
        self.assertTrue(self.phone.verified)
        self.assertEqual(
            list(
                LogEntry.objects.filter(object_id=str(self.phone.pk))
                .order_by("action_time")
                .values_list("change_message", flat=True)
            ),
            [
                "Sent an SMS verification code (staff check).",
                "Verified with an SMS code the member read back to staff.",
            ],
        )

    def test_a_wrong_code_does_not_verify(self):
        self.send()

        response = self.enter(WRONG_CODE)

        self.assertEqual(response.redirect_chain[-1][0], _verify_url(self.phone))
        self.assertIn("That code is wrong or has expired", self.texts(response)[0])
        self.phone.refresh_from_db()
        self.assertFalse(self.phone.verified)

    def test_too_many_wrong_codes_spend_the_code(self):
        self.send()

        answers = [self.texts(self.enter(WRONG_CODE))[0] for _ in range(5)]

        self.assertIn("Too many wrong codes. Send a new code.", answers[-1])
        self.assertFalse(self.enter(SMS_CODE).context["contact"].verified)

    def test_a_malformed_code_is_not_a_guess(self):
        self.send()

        response = self.enter("12ab")

        self.assertIn("Enter the 6-digit code", self.texts(response)[0])
        self.assertEqual(PhoneVerificationChallenge.objects.get().attempts, 0)

    def test_a_code_without_a_send_is_refused(self):
        response = self.enter(SMS_CODE)

        self.assertIn("That code is wrong or has expired", self.texts(response)[0])

    def test_an_already_verified_number_is_sent_nothing(self):
        self.mark_verified(self.phone)

        page = self.client.get(_verify_url(self.phone))
        response = self.send()

        self.assertContains(page, "This number is already verified.")
        self.assertEqual(self.texts(response), ["This phone number is already verified."])
        self.publish.assert_not_called()

    @override_settings(SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=60)
    def test_the_per_number_cooldown_stops_a_double_send(self):
        self.send()
        response = self.send()

        self.assertEqual(self.texts(response), ["The code was not sent: Please wait before requesting another code."])
        self.publish.assert_called_once()

    def test_a_delivery_failure_is_reported(self):
        self.publish.side_effect = PhoneVerificationDeliveryError("SMS is not configured.", outcome="permanent")

        response = self.send()

        self.assertEqual(self.texts(response), ["The code was not sent: SMS is not configured."])
        self.assertFalse(LogEntry.objects.exists())

    def test_a_member_less_number_has_no_account_to_verify(self):
        orphan = ContactPhone.objects.create(member=None, phone_number="2095550155", region="1-US")

        response = self.client.get(_verify_url(orphan), follow=True)

        self.assertEqual(response.redirect_chain[-1][0], _change_url(orphan))
        self.assertIn("belongs to no member", self.texts(response)[0])

    def test_an_unknown_phone_is_404(self):
        self.assertEqual(self.client.get(_verify_url(self.member)).status_code, 404)

    def test_staff_without_the_members_app_are_refused(self):
        staffer = Member.objects.create_user(password=None, is_staff=True, is_active=True)
        staffer.admin_apps = ["event"]
        staffer.save(update_fields=["admin_apps"])
        self.client.force_login(staffer)

        self.assertEqual(self.client.get(_verify_url(self.phone)).status_code, 403)
        self.assertEqual(self.client.post(_verify_url(self.phone), {"action": "send"}).status_code, 403)
        self.publish.assert_not_called()

    def test_only_an_i2g_master_may_verify_a_staff_accounts_number(self):
        staff_owner = Member.objects.create_user(password=None, is_staff=True, is_active=True)
        staff_phone = ContactPhone.objects.create(member=staff_owner, phone_number="2095550166", region="1-US")
        staffer = Member.objects.create_user(password=None, is_staff=True, is_active=True)
        staffer.admin_apps = ["authn"]
        staffer.save(update_fields=["admin_apps"])
        self.client.force_login(staffer)

        self.assertEqual(self.client.post(_verify_url(staff_phone), {"action": "send"}).status_code, 403)
        self.assertEqual(self.client.get(_verify_url(self.phone)).status_code, 200)
        self.publish.assert_not_called()

    def test_anonymous_visitors_are_sent_to_the_admin_login(self):
        self.client.logout()

        response = self.client.get(_verify_url(self.phone))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)


class SameMemberTests(TestCase):
    def test_a_uuid_and_its_string_name_the_same_member(self):
        member = Member.objects.create_user(password=None, is_active=True)

        self.assertTrue(same_member(member.pk, str(member.pk)))
        self.assertTrue(same_member(None, None))
        self.assertFalse(same_member(member.pk, None))
        self.assertFalse(same_member(str(member.pk), Member.objects.create_user(password=None, is_active=True).pk))


class SmsSignInStatusTests(TestCase):
    def test_nothing_to_show_before_a_phone_is_saved(self):
        self.assertEqual(sms_sign_in_status(None), "-")
        self.assertEqual(sms_sign_in_status(ContactPhone(phone_number="2095550177", region="1-US")), "-")

    def test_a_member_less_number_gets_no_verification_link(self):
        orphan = ContactPhone.objects.create(member=None, phone_number="2095550188", region="1-US")

        html = sms_sign_in_status(orphan)

        self.assertIn("Unverified · no SMS sign-in", html)
        self.assertNotIn("Verify by SMS code", html)

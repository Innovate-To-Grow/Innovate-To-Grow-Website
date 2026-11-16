from django.contrib.admin.models import LogEntry
from django.test import TestCase, override_settings

from apps.authn.admin.members.contact.phone_verification import same_member
from apps.authn.models import ContactPhone, Member, PhoneVerificationChallenge
from apps.authn.services.sms import PhoneVerificationDeliveryError
from apps.authn.tests.admin.members.security.phone.test_phone_verification_admin import (
    AdminPhoneTestCase,
    _change_url,
    _verify_url,
)
from apps.authn.tests.sms_provider import SMS_CODE, WRONG_CODE, patch_sms_provider


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

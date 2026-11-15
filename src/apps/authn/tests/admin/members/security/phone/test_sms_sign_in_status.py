from django.test import TestCase

from apps.authn.admin.members.contact.phone_verification import sms_sign_in_status
from apps.authn.models import ContactPhone


class SmsSignInStatusTests(TestCase):
    def test_nothing_to_show_before_a_phone_is_saved(self):
        self.assertEqual(sms_sign_in_status(None), "-")
        self.assertEqual(sms_sign_in_status(ContactPhone(phone_number="2095550177", region="1-US")), "-")

    def test_a_member_less_number_gets_no_verification_link(self):
        orphan = ContactPhone.objects.create(member=None, phone_number="2095550188", region="1-US")

        html = sms_sign_in_status(orphan)

        self.assertIn("Unverified · no SMS sign-in", html)
        self.assertNotIn("Verify by SMS code", html)

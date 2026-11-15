from unittest.mock import patch

from django.core import mail

from apps.authn.tests.services.members.import_safety.test_import_members_safety import _ImportCase


class NoMessagesSentTests(_ImportCase):
    def test_adding_contacts_sends_no_mail_and_no_sms(self):
        self._email("old@example.com")
        self._phone("2095550001")

        with patch("apps.authn.services.sms.sns_verify._publish_sms") as sms:
            result = self._update({"Secondary Email": "new@example.com", "Phone Number": "+12095550002"})

        self.assertEqual(result.updated_count, 1)
        self.assertEqual(mail.outbox, [])
        sms.assert_not_called()

"""The subject allow-list is checked before any key read, token request or socket."""

from unittest.mock import patch

from django.test import TestCase

from apps.core.services.email.gmail import auth
from apps.core.services.email.gmail.access import GmailScopeError, credential_for, require_subject
from apps.core.services.email.gmail.key import stored_key
from apps.core.tests.gmail_api_helpers import SUBJECT, make_config, reset_gmail_state

CONNECTION = "apps.core.services.email.transport.HTTPSConnection"


class SubjectAllowListTests(TestCase):
    def setUp(self):
        reset_gmail_state()
        self.config = make_config()

    def test_a_listed_subject_passes_case_insensitively(self):
        subject = require_subject(self.config, " I2G@G.UCMERCED.EDU ")
        self.assertEqual(subject.address, SUBJECT)
        self.assertNotIn("_issued", repr(subject))

    def test_an_unlisted_address_is_refused_without_store_reads_or_sockets(self):
        with patch.object(stored_key, "read_key") as read, patch(CONNECTION) as connection:
            for address in ("someone@g.ucmerced.edu", "", "i2g@g.ucmerced.edu.evil.example"):
                with self.subTest(address=address), self.assertRaises(GmailScopeError):
                    require_subject(self.config, address)
        read.assert_not_called()
        connection.assert_not_called()

    def test_tokens_need_a_subject_from_the_allow_list_check(self):
        credential = credential_for(self.config)
        with patch.object(stored_key, "read_key") as read, patch(CONNECTION) as connection:
            with self.assertRaises(TypeError):
                auth.get_access_token(credential, auth.AllowedSubject(SUBJECT))
            with self.assertRaises(TypeError):
                auth.request_token(credential, None, auth.AllowedSubject(SUBJECT), timeout=1)
        read.assert_not_called()
        connection.assert_not_called()

    def test_a_config_without_a_key_has_no_credential(self):
        from apps.core.services.email import PermanentEmailDeliveryError

        with self.assertRaises(PermanentEmailDeliveryError):
            credential_for(make_config(active=False, key=False))

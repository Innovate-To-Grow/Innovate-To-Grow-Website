"""The Gmail API config: one active row, readiness, the subject allow-list, no secret columns, and activation."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.core.models import GmailApiProviderConfig, GmailApiSubject
from apps.core.tests.gmail_api_helpers import SUBJECT, make_config

GMAIL_API = {
    "request_timeout_seconds": 15,
    "max_response_bytes": 65536,
    "max_recipients_per_message": 100,
    "max_message_bytes": 1_000_000,
    "upload_max_bytes": 36_700_160,
    "assertion_lifetime_seconds": 300,
    "token_max_lifetime_seconds": 3600,
    "token_expiry_margin_seconds": 300,
    "key_max_input_bytes": 16384,
    "min_rsa_key_bits": 2048,
    "key_check_timeout_seconds": 10,
    "access_check_timeout_seconds": 10,
}


class NoSecretColumnsTests(TestCase):
    def test_only_the_store_pointer_and_public_ids_look_like_key_fields(self):
        names = {field.name for field in GmailApiProviderConfig._meta.get_fields()}
        suspicious = {name for name in names if any(part in name for part in ("key", "secret", "private"))}
        self.assertEqual(suspicious, {"key_secret_ref", "key_version_id", "key_id", "key_installed_at"})
        for name in ("key_secret_ref", "key_version_id", "key_id"):
            field = GmailApiProviderConfig._meta.get_field(name)
            with self.subTest(name=name):
                # A PEM key is well over 1,500 characters: none of these columns can hold one.
                self.assertLessEqual(field.max_length, 512)
        for field in GmailApiProviderConfig._meta.get_fields():
            with self.subTest(field=field.name):
                self.assertNotEqual(field.get_internal_type(), "TextField")
                self.assertNotEqual(field.get_internal_type(), "JSONField")

    def test_key_facts_must_be_well_formed_to_count_as_configured(self):
        config = make_config(active=False)
        self.assertTrue(config.key_configured)
        for field, value in (
            ("service_account_email", "someone@example.com"),
            ("project_id", "another-project"),
            ("client_id", "12ab"),
            ("key_id", "-----BEGIN PRIVATE KEY-----"),
            ("key_version_id", "short"),
            ("key_secret_ref", ""),
        ):
            with self.subTest(field=field):
                original = getattr(config, field)
                setattr(config, field, value)
                self.assertFalse(config.key_configured)
                setattr(config, field, original)


class ActiveRowTests(TestCase):
    def test_one_active_config_and_activation_needs_a_key(self):
        first = make_config()
        second = make_config(subjects=("other@g.ucmerced.edu",))
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(GmailApiProviderConfig.load(), second)

        keyless = make_config(active=False, key=False)
        keyless.is_active = True
        with self.assertRaises(ValidationError) as caught:
            keyless.save()
        self.assertIn("is_active", caught.exception.message_dict)

    def test_load_without_an_active_row_is_unsaved_and_not_ready(self):
        config = GmailApiProviderConfig.load()
        self.assertTrue(config._state.adding)
        self.assertFalse(config.is_configured)
        self.assertFalse(config.allows(SUBJECT))
        self.assertFalse(config.sending_ready(SUBJECT))

    def test_readiness_needs_active_key_and_the_from_address_on_the_list(self):
        config = make_config()
        self.assertTrue(config.is_configured)
        self.assertTrue(config.sending_ready("I2G@G.UCMERCED.EDU "))
        self.assertFalse(config.sending_ready("someone-else@g.ucmerced.edu"))
        config.subjects.all().delete()
        self.assertFalse(config.is_configured)

    @override_settings(GMAIL_API=GMAIL_API)
    def test_limits_can_be_lowered_but_not_raised_above_settings(self):
        config = make_config(active=False)
        config.max_recipients_per_message = 101
        with self.assertRaises(ValidationError) as caught:
            config.full_clean()
        self.assertIn("max_recipients_per_message", caught.exception.message_dict)
        config.max_recipients_per_message = 100
        config.max_message_bytes = 1_000_001
        with self.assertRaises(ValidationError) as caught:
            config.full_clean()
        self.assertIn("max_message_bytes", caught.exception.message_dict)
        config.max_message_bytes = 10
        config.full_clean()

    @override_settings(GMAIL_API=GMAIL_API)
    def test_defaults_come_from_settings(self):
        config = GmailApiProviderConfig()
        self.assertEqual(config.max_recipients_per_message, 100)
        self.assertEqual(config.max_message_bytes, 1_000_000)
        self.assertEqual(config.credential_mail, GmailApiProviderConfig.CredentialMail.SEND)


class SubjectAllowListTests(TestCase):
    def test_subjects_are_normalized_and_unique_per_config(self):
        config = make_config(subjects=())
        subject = GmailApiSubject(config=config, subject="  I2G@G.UCMerced.edu ")
        subject.full_clean()
        subject.save()
        self.assertEqual(subject.subject, SUBJECT)
        self.assertTrue(config.allows("i2g@g.ucmerced.edu"))
        with transaction.atomic(), self.assertRaises(IntegrityError):
            GmailApiSubject.objects.create(config=config, subject="i2g@G.ucmerced.edu")

    def test_tagged_non_ascii_and_display_name_addresses_are_refused(self):
        config = make_config(subjects=())
        for value in ("i2g+news@g.ucmerced.edu", "jürgen@g.ucmerced.edu", "I2G <i2g@g.ucmerced.edu>", "nobody"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                GmailApiSubject(config=config, subject=value).full_clean()

    def test_changing_a_subject_clears_its_verification(self):
        config = make_config()
        subject = config.subjects.get()
        self.assertIsNotNone(subject.verified_at)
        subject.subject = "other@g.ucmerced.edu"
        subject.save()
        subject.refresh_from_db()
        self.assertIsNone(subject.verified_at)

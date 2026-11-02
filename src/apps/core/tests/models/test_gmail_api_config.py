"""The Gmail API config: one active row, readiness, the subject allow-list, no secret columns, and activation."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import EmailServiceConfig, GmailApiProviderConfig, GmailApiSubject
from apps.core.models.base.service_credentials.email import GMAIL_ACTIVATION_REQUIRED
from apps.core.tests.gmail_api_helpers import SUBJECT, make_config, make_email_config

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


class ActivationTests(TestCase):
    def email(self, **fields):
        values = {
            "name": "Mail",
            "is_active": True,
            "provider": EmailServiceConfig.Provider.GMAIL,
            "from_email": SUBJECT,
        }
        values.update(fields)
        return EmailServiceConfig(**values)

    def test_switching_to_gmail_needs_a_passed_check_and_a_verified_from(self):
        config = make_config()
        self.email().validate_activation()  # checked and verified after the key was installed

        config.access_checked_at = config.key_installed_at - timedelta(minutes=1)
        config.save()
        with self.assertRaises(ValidationError) as caught:
            self.email().validate_activation()
        self.assertEqual(caught.exception.message_dict["provider"], [GMAIL_ACTIVATION_REQUIRED])

        config.access_checked_at = timezone.now()
        config.save()
        config.subjects.update(verified_at=None)
        with self.assertRaises(ValidationError):
            self.email().validate_activation()

    def test_delivery_configured_needs_readiness_only(self):
        make_config(checked=False, verified=False)
        email = make_email_config()
        self.assertTrue(email.delivery_configured)
        self.assertEqual(email.delivery_summary, f"Gmail API ({SUBJECT})")
        with self.assertRaises(ValidationError):
            self.email().validate_activation()

    def test_a_from_address_off_the_list_is_refused(self):
        make_config()
        with self.assertRaises(ValidationError):
            self.email(from_email="someone@g.ucmerced.edu").validate_activation()
        email = make_email_config(from_email="someone@g.ucmerced.edu")
        self.assertFalse(email.delivery_configured)
        self.assertEqual(email.delivery_summary, "Not configured")

    def test_unrelated_saves_while_already_sending_need_only_readiness(self):
        config = make_config()
        email = make_email_config()
        config.key_installed_at = timezone.now()  # a rotation clears the evidence until the next check
        config.save()
        email.from_name = "I2G"
        email.validate_activation()
        email.from_email = "other@g.ucmerced.edu"
        GmailApiSubject.objects.create(config=config, subject="other@g.ucmerced.edu")
        with self.assertRaises(ValidationError):
            email.validate_activation()  # a new From address is a go-live of its own

    def test_activating_a_standby_while_email_sends_through_gmail_needs_its_evidence(self):
        make_config()
        make_email_config()
        standby = make_config(active=False, checked=False)
        standby.is_active = True
        with self.assertRaises(ValidationError) as caught:
            standby.save()
        self.assertIn("is_active", caught.exception.message_dict)
        standby.access_checked_at = timezone.now()
        standby.save()
        self.assertEqual(GmailApiProviderConfig.load(), standby)

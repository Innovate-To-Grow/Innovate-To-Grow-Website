from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailServiceConfig, GmailApiProviderConfig, GmailApiSubject
from apps.core.models.base.service_credentials.email import GMAIL_ACTIVATION_REQUIRED
from apps.core.tests.gmail_api_helpers import SUBJECT, make_config, make_email_config


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

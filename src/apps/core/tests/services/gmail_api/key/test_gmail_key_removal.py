from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.test import TestCase

from apps.core.models import EmailServiceConfig
from apps.core.services.email.gmail.key import removal
from apps.core.services.email.gmail.key.install import KeyChangeError
from apps.core.tests.gmail_api_helpers import (
    make_config,
    make_email_config,
    reset_gmail_state,
)
from apps.event.tests.helpers import make_superuser


class RemovalTests(TestCase):
    def setUp(self):
        reset_gmail_state()
        self.actor = make_superuser()

    def test_removal_unpins_deactivates_and_can_switch_to_ses(self):
        config = make_config()
        email = make_email_config()
        with patch.object(EmailServiceConfig, "validate_activation"):
            result = removal.remove_key(config, reason="Key leaked", actor=self.actor, switch_to_ses=True)
        config.refresh_from_db()
        self.assertTrue(result.provider_switched)
        self.assertFalse(config.is_active or config.key_configured or config.key_installed_at)
        self.assertEqual(EmailServiceConfig.objects.get(pk=email.pk).provider, "ses")
        self.assertIn("Key leaked", LogEntry.objects.get().change_message)

    def test_removal_without_a_ready_ses_keeps_the_provider(self):
        config = make_config()
        email = make_email_config()
        result = removal.remove_key(config, reason="Rotation gone wrong", actor=self.actor, switch_to_ses=True)
        self.assertFalse(result.provider_switched)
        self.assertEqual(EmailServiceConfig.objects.get(pk=email.pk).provider, "gmail")

    def test_nothing_to_remove(self):
        with self.assertRaises(KeyChangeError):
            removal.remove_key(make_config(active=False, key=False), reason="x", actor=self.actor)

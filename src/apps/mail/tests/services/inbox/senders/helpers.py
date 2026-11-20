"""Fixtures for the reply sender tests: a clean sender configuration, Notification Delivery on SES, and reply accounts."""

from django.core.cache import cache

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GmailAccessAccount,
    GmailApiProviderConfig,
    MicrosoftGraphProviderConfig,
)
from apps.mail.tests.services.inbox.accounts.helpers import gmail_account

DEFAULT_ADDRESS = "notify@ucmerced.edu"
WORKSPACE = "i2g@g.ucmerced.edu"


class SenderFixtureMixin:
    def setUp(self):
        super().setUp()
        # The identities are cached per container (``SENDERS_CACHE_KEY``).
        cache.clear()
        self.addCleanup(cache.clear)
        for model in (EmailServiceConfig, MicrosoftGraphProviderConfig, GmailApiProviderConfig, GmailAccessAccount):
            model.objects.all().delete()

    def default_sender(self, from_email=DEFAULT_ADDRESS):
        """Notification Delivery on SES, which is ready once AWS credentials are active."""
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        return EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="ses", from_email=from_email, from_name="I2G"
        )

    def reply_account(self, username="reply@gmail.com", **overrides):
        return gmail_account(username, **{"is_active": False, "reply_enabled": True, **overrides})

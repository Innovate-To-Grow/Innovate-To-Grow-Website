"""The "gmail" provider resolves from Notification Delivery, and the allow-list is re-checked on every send."""

from django.test import TestCase

from apps.core.models import EmailServiceConfig
from apps.core.services.email import EmailMessage, PermanentEmailDeliveryError, deliver_email, resolve_provider
from apps.core.services.email.gmail import GmailProvider, GmailScopeError
from apps.core.services.email.registry import active_rate_target
from apps.core.tests.gmail_api_helpers import (
    SUBJECT,
    FakePost,
    make_config,
    make_email_config,
    reset_gmail_state,
    send_response,
    stored_config,
    token_response,
)


class GmailRegistryTests(TestCase):
    def setUp(self):
        reset_gmail_state()

    def test_gmail_resolves_to_the_subject_of_the_from_address(self):
        config = make_config()
        provider = resolve_provider(make_email_config())
        self.assertIsInstance(provider, GmailProvider)
        self.assertEqual(provider.subject.address, SUBJECT)
        self.assertEqual((provider.max_recipients, provider.credential_mail), (500, config.credential_mail))
        self.assertEqual(active_rate_target(), ("gmail_api_send", SUBJECT))

    def test_a_missing_or_keyless_config_is_permanent(self):
        email = make_email_config()
        with self.assertRaises(PermanentEmailDeliveryError):
            resolve_provider(email)
        make_config(key=False, active=False)
        with self.assertRaises(PermanentEmailDeliveryError):
            resolve_provider(email)
        self.assertIsNone(active_rate_target())

    def test_a_from_address_outside_the_list_is_refused(self):
        make_config()
        with self.assertRaises(GmailScopeError):
            resolve_provider(make_email_config(from_email="other@g.ucmerced.edu"))

    def test_removing_a_subject_takes_effect_at_the_next_send_even_with_a_cached_token(self):
        config = stored_config()
        email = make_email_config()
        post = FakePost(token_response(), send_response()).install(self)
        message = EmailMessage(subject="Hi", to=("a@example.com",), text_body="Hi")
        deliver_email(message, config=email)
        config.subjects.all().delete()
        with self.assertRaises(PermanentEmailDeliveryError):
            deliver_email(message, config=EmailServiceConfig.objects.get(pk=email.pk))
        self.assertEqual(len(post.calls), 2)

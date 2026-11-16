from django.test import TestCase
from django.urls import reverse

from apps.mail.tests.services.delivery.providers.test_delivery_provider_labels import PROVIDERS, ProviderFixtureMixin


class TestEmailFormHelpTextTests(ProviderFixtureMixin, TestCase):
    """The send-a-test-email forms say which provider will carry the message."""

    def setUp(self):
        self.create_provider_configs()

    def assert_names_only(self, response, label):
        self.assertContains(response, f"through {label}.")
        for _provider, other in PROVIDERS:
            if other != label:
                self.assertNotContains(response, f"through {other}.")

    def test_notification_delivery_form_names_the_active_provider(self):
        for provider, label in PROVIDERS:
            with self.subTest(provider=provider):
                self.use_provider(provider)

                response = self.client.get(reverse("admin:mail_settings_test_email"))

                self.assert_names_only(response, label)

    def test_credential_admin_form_names_the_active_provider(self):
        for provider, label in PROVIDERS:
            with self.subTest(provider=provider):
                self.use_provider(provider)

                response = self.client.get(reverse("admin:core_awscredentialconfig_test_email"))

                self.assert_names_only(response, label)

"""Installing and removing an AI provider's API key from its admin pages."""

import uuid
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import Client, RequestFactory

from apps.core.services.credential_store import CredentialStoreError
from apps.system_intelligence.admin.config.provider_admin import LLMProviderConfigAdmin
from apps.system_intelligence.models import LLMProviderConfig
from apps.system_intelligence.services.agents.providers.keys import KEY_FORMAT, read_api_key
from apps.system_intelligence.tests.admin.config.test_provider_admin import (
    TEST_KEY,
    ProviderAdminTestCase,
    action_url,
    change_url,
    make_provider,
)

NEW_KEY = "sk-new-key-ffff-7777"  # noqa: S105 - test fixture, not a real key


def _messages(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


class InstallKeyActionTests(ProviderAdminTestCase):
    def test_get_renders_an_empty_password_box(self):
        provider = make_provider(key=TEST_KEY)
        response = self.client.get(action_url("install_key_action", provider))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Install API key: DeepSeek")
        self.assertContains(response, 'type="password"')
        self.assertContains(response, 'name="api_key"')
        self.assertContains(response, 'autocomplete="new-password"')
        self.assertContains(response, "ends …abcd")
        self.assertContains(response, change_url(provider))
        self.assertNotContains(response, TEST_KEY)

    def test_post_stores_the_key_and_pins_version_and_hint(self):
        provider = make_provider()
        response = self.client.post(action_url("install_key_action", provider), {"api_key": f"  {NEW_KEY}  "})
        self.assertRedirects(response, change_url(provider), fetch_redirect_response=False)
        provider.refresh_from_db()
        self.assertTrue(provider.key_configured)
        self.assertTrue(provider.key_secret_ref)
        self.assertTrue(provider.key_version_id)
        self.assertEqual(provider.key_hint, "7777")
        self.assertIsNotNone(provider.key_installed_at)
        self.assertFalse(provider.is_enabled)
        self.assertEqual(read_api_key(provider), NEW_KEY)
        self.assertEqual(
            _messages(response), ["Installed an API key ending in …7777. Test it, then enable the provider."]
        )

    def test_reinstalling_replaces_the_pinned_version(self):
        provider = make_provider(key=TEST_KEY)
        old_version = provider.key_version_id
        self.client.post(action_url("install_key_action", provider), {"api_key": NEW_KEY})
        provider.refresh_from_db()
        self.assertNotEqual(provider.key_version_id, old_version)
        self.assertEqual(read_api_key(provider), NEW_KEY)

    def test_invalid_key_is_rejected_and_never_echoed(self):
        provider = make_provider()
        bad_key = "sk bad key with-spaces-MARKER"  # noqa: S105 - test fixture
        response = self.client.post(action_url("install_key_action", provider), {"api_key": bad_key})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, KEY_FORMAT)
        self.assertNotContains(response, "MARKER")
        provider.refresh_from_db()
        self.assertFalse(provider.key_configured)

    def test_blank_key_is_required(self):
        provider = make_provider()
        response = self.client.post(action_url("install_key_action", provider), {"api_key": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].errors["api_key"], ["This field is required."])

    def test_store_failure_is_shown_on_the_form(self):
        provider = make_provider()
        failing = patch(
            "apps.system_intelligence.services.agents.providers.keys.get_store",
            side_effect=CredentialStoreError("store offline"),
        )
        with failing:
            response = self.client.post(action_url("install_key_action", provider), {"api_key": NEW_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The API key could not be stored: store offline")
        self.assertNotContains(response, NEW_KEY)
        provider.refresh_from_db()
        self.assertFalse(provider.key_configured)

    def test_post_requires_a_csrf_token(self):
        provider = make_provider()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.superuser)
        self.assertEqual(client.post(action_url("install_key_action", provider), {"api_key": NEW_KEY}).status_code, 403)
        provider.refresh_from_db()
        self.assertFalse(provider.key_configured)

    def test_key_is_marked_as_a_sensitive_post_parameter(self):
        provider = make_provider()
        request = RequestFactory().post("/", {"api_key": NEW_KEY})
        request.user = self.superuser
        request.session = {}
        request._messages = FallbackStorage(request)
        request._dont_enforce_csrf_checks = True
        admin = LLMProviderConfigAdmin(LLMProviderConfig, AdminSite())
        response = admin.install_key_action(request, str(provider.pk))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(request.sensitive_post_parameters, ("api_key",))

    def test_unknown_provider_and_unsupported_method_are_404(self):
        provider = make_provider()
        missing = action_url("install_key_action", provider).replace(str(provider.pk), str(uuid.uuid4()))
        self.assertEqual(self.client.get(missing).status_code, 404)
        self.assertEqual(self.client.put(action_url("install_key_action", provider)).status_code, 404)


class RemoveKeyActionTests(ProviderAdminTestCase):
    def test_get_renders_the_confirmation(self):
        provider = make_provider(key=TEST_KEY)
        response = self.client.get(action_url("remove_key_action", provider))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Remove API key: DeepSeek")
        self.assertContains(response, 'name="confirm"')
        self.assertContains(response, "Remove key")

    def test_post_without_confirmation_keeps_the_key(self):
        provider = make_provider(key=TEST_KEY, is_enabled=True)
        response = self.client.post(action_url("remove_key_action", provider), {})
        self.assertEqual(response.status_code, 200)
        self.assertIn("confirm", response.context["form"].errors)
        provider.refresh_from_db()
        self.assertTrue(provider.key_configured)
        self.assertTrue(provider.is_enabled)

    def test_confirmed_post_unpins_the_key_and_disables(self):
        provider = make_provider(key=TEST_KEY, is_enabled=True)
        response = self.client.post(action_url("remove_key_action", provider), {"confirm": "on"})
        self.assertRedirects(response, change_url(provider), fetch_redirect_response=False)
        provider.refresh_from_db()
        self.assertFalse(provider.key_configured)
        self.assertEqual((provider.key_secret_ref, provider.key_version_id, provider.key_hint), ("", "", ""))
        self.assertIsNone(provider.key_installed_at)
        self.assertFalse(provider.is_enabled)
        self.assertEqual(_messages(response), ["Removed the API key and disabled the provider."])

"""The AI provider admin: list and change pages, and saving (as an Admin).

``make_provider`` / ``action_url`` / ``post_data`` / ``ProviderAdminTestCase`` are shared with the other provider tests.
"""

from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.services.credential_store import memory
from apps.event.tests.helpers import make_admin
from apps.system_intelligence.admin.config.provider_admin import LLMProviderConfigAdmin
from apps.system_intelligence.models import LLMProviderConfig
from apps.system_intelligence.models.llm_provider import DISABLED_NEEDS_KEY
from apps.system_intelligence.services.agents.providers.keys import install_api_key
from apps.system_intelligence.tests.admin.base import rendered_badge

CHANGELIST_URL = "/admin/system_intelligence/llmproviderconfig/"
RUN_PROBE = "apps.system_intelligence.services.agents.run_tool_free_agent"
TEST_KEY = "fake-fake-fake-abcd"  # noqa: S105 - test fixture, not a real key


def make_provider(*, key=None, **fields):
    """A saved provider (DeepSeek preset by default); *key* installs an API key in the memory store."""
    fields = {"name": "DeepSeek", "preset": LLMProviderConfig.Preset.DEEPSEEK, **fields}
    enabled = fields.pop("is_enabled", False)
    provider = LLMProviderConfig.objects.create(**fields)
    if key:
        install_api_key(provider, key)
    if enabled:
        provider.is_enabled = True
        provider.save(update_fields=["is_enabled", "updated_at"])
    return provider


def action_url(name, provider):
    return reverse(f"admin:system_intelligence_llmproviderconfig_{name}", args=[provider.pk])


def change_url(provider):
    return reverse("admin:system_intelligence_llmproviderconfig_change", args=[provider.pk])


class ProviderAdminTestCase(TestCase):
    def setUp(self):
        cache.clear()
        memory.reset()
        self.addCleanup(memory.reset)
        self.admin_user = make_admin()
        self.client.force_login(self.admin_user)


def post_data(provider, **overrides):
    data = {
        "name": provider.name,
        "preset": provider.preset,
        "api_format": provider.api_format,
        "base_url": provider.base_url,
        "request_timeout_seconds": provider.request_timeout_seconds,
        "context_window_tokens": provider.context_window_tokens,
    }
    if provider.is_enabled:
        data["is_enabled"] = "on"
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


class ProviderAdminDisplayTests(TestCase):
    def setUp(self):
        self.admin = LLMProviderConfigAdmin(LLMProviderConfig, AdminSite())

    def test_status_badge(self):
        enabled, disabled = LLMProviderConfig(is_enabled=True), LLMProviderConfig(is_enabled=False)
        self.assertEqual(rendered_badge(self.admin.status_badge, enabled), ("Enabled", "success"))
        self.assertEqual(rendered_badge(self.admin.status_badge, disabled), ("Disabled", "danger"))

    def test_endpoint_display_for_presets_custom_and_unknown(self):
        self.assertEqual(self.admin.endpoint_display(LLMProviderConfig(preset="deepseek")), "https://api.deepseek.com")
        custom = LLMProviderConfig(preset="custom", api_format="anthropic", base_url="https://gw.example.com")
        self.assertEqual(self.admin.endpoint_display(custom), "Anthropic Messages https://gw.example.com")
        self.assertEqual(self.admin.endpoint_display(LLMProviderConfig(preset="retired", base_url="")), "—")

    def test_key_display(self):
        self.assertEqual(self.admin.key_display(LLMProviderConfig()), "Not installed")
        installed = LLMProviderConfig(key_secret_ref="memory:x", key_version_id="v1", key_hint="abcd")
        self.assertEqual(self.admin.key_display(installed), "Installed (ends …abcd)")


class ProviderAdminPageTests(ProviderAdminTestCase):
    def test_changelist_lists_providers_with_status_and_key_state(self):
        make_provider(key=TEST_KEY, is_enabled=True)
        make_provider(name="Gateway", preset="custom", base_url="https://gateway.example.com/v1")
        response = self.client.get(CHANGELIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DeepSeek")
        self.assertContains(response, "https://api.deepseek.com")
        self.assertContains(response, "OpenAI-compatible (Chat Completions) https://gateway.example.com/v1")
        self.assertContains(response, "Installed (ends …abcd)")
        self.assertContains(response, "Not installed")
        self.assertContains(response, "Enabled")
        self.assertContains(response, "Disabled")
        self.assertNotContains(response, TEST_KEY)

    def test_change_page_links_key_actions_and_has_no_key_input(self):
        provider = make_provider(key=TEST_KEY)
        response = self.client.get(change_url(provider))
        self.assertEqual(response.status_code, 200)
        for name in ("install_key_action", "remove_key_action", "test_connection_action"):
            self.assertContains(response, action_url(name, provider))
        self.assertContains(response, "Installed (ends …abcd)")
        self.assertNotContains(response, 'name="api_key"')
        self.assertNotContains(response, 'name="key_secret_ref"')
        self.assertNotContains(response, 'name="key_version_id"')
        self.assertNotContains(response, TEST_KEY)
        self.assertNotContains(response, provider.key_version_id)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class ProviderAdminSaveTests(ProviderAdminTestCase):
    def test_add_page_creates_a_disabled_provider(self):
        data = post_data(LLMProviderConfig(name="Kimi", preset="moonshot"))
        response = self.client.post(reverse("admin:system_intelligence_llmproviderconfig_add"), data)
        self.assertEqual(response.status_code, 302)
        provider = LLMProviderConfig.objects.get(name="Kimi")
        self.assertFalse(provider.is_enabled)
        self.assertFalse(provider.key_configured)

    def test_enabling_without_a_key_is_rejected(self):
        provider = make_provider()
        response = self.client.post(change_url(provider), post_data(provider, is_enabled="on"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(DISABLED_NEEDS_KEY, response.context["adminform"].form.errors["is_enabled"])
        provider.refresh_from_db()
        self.assertFalse(provider.is_enabled)

    def test_renaming_keeps_the_key_and_enabled_state(self):
        provider = make_provider(key=TEST_KEY, is_enabled=True)
        response = self.client.post(change_url(provider), post_data(provider, name="DeepSeek Prod"))
        self.assertEqual(response.status_code, 302)
        provider.refresh_from_db()
        self.assertEqual(provider.name, "DeepSeek Prod")
        self.assertTrue(provider.key_configured)
        self.assertTrue(provider.is_enabled)

    def test_endpoint_change_unpins_the_key_and_disables(self):
        provider = make_provider(key=TEST_KEY, is_enabled=True)
        data = post_data(provider, preset="custom", base_url="https://gateway.example.com/v1/")
        response = self.client.post(change_url(provider), data)
        self.assertEqual(response.status_code, 302)
        provider.refresh_from_db()
        self.assertEqual(provider.base_url, "https://gateway.example.com/v1")
        self.assertFalse(provider.key_configured)
        self.assertEqual((provider.key_hint, provider.key_installed_at), ("", None))
        self.assertFalse(provider.is_enabled)

    def test_private_custom_base_url_is_rejected(self):
        provider = make_provider()
        data = post_data(provider, preset="custom", base_url="https://169.254.169.254/v1")
        response = self.client.post(change_url(provider), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("base_url", response.context["adminform"].form.errors)

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.system_intelligence.models import LLMProviderConfig
from apps.system_intelligence.models.llm_provider import DISABLED_NEEDS_KEY
from apps.system_intelligence.services.agents.providers.endpoints import NEEDS_HTTPS, PRIVATE_HOST

from . import make_keyed_provider, make_provider

Preset = LLMProviderConfig.Preset
KEY_FIELDS = ("key_secret_ref", "key_version_id", "key_hint")


class LLMProviderPropertiesTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_str_and_key_configured(self):
        self.assertEqual(str(LLMProviderConfig(name="A", is_enabled=True)), "A")
        self.assertEqual(str(LLMProviderConfig(name="A")), "A (disabled)")
        self.assertFalse(LLMProviderConfig(key_secret_ref="arn").key_configured)
        self.assertFalse(LLMProviderConfig(key_version_id="v").key_configured)
        self.assertTrue(LLMProviderConfig(key_secret_ref="arn", key_version_id="v").key_configured)

    def test_effective_endpoint_for_preset_and_custom(self):
        preset = LLMProviderConfig(preset=Preset.ANTHROPIC, api_format="openai", base_url="https://evil.example.com")
        self.assertFalse(preset.is_custom)
        self.assertEqual(preset.effective_api_format, "anthropic")
        self.assertEqual(preset.effective_base_url, "https://api.anthropic.com")
        custom = LLMProviderConfig(preset=Preset.CUSTOM, api_format="anthropic", base_url="https://gw.example.com")
        self.assertTrue(custom.is_custom)
        self.assertEqual(custom.effective_api_format, "anthropic")
        self.assertEqual(custom.effective_base_url, "https://gw.example.com")


class LLMProviderCleanTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_preset_forces_format_and_clears_base_url(self):
        provider = LLMProviderConfig(
            name="Kimi", preset=Preset.MOONSHOT_ANTHROPIC, api_format="openai", base_url="https://x.example.com"
        )
        provider.clean()
        self.assertEqual((provider.api_format, provider.base_url), ("anthropic", ""))

    def test_custom_base_url_is_normalized(self):
        provider = LLMProviderConfig(name="GW", preset=Preset.CUSTOM, base_url=" https://gw.example.com/v1/ ")
        provider.clean()
        self.assertEqual(provider.base_url, "https://gw.example.com/v1")

    def test_custom_base_url_errors(self):
        for url, message in (("http://gw.example.com", NEEDS_HTTPS), ("https://10.0.0.1", PRIVATE_HOST)):
            with self.subTest(url=url):
                provider = LLMProviderConfig(name="GW", preset=Preset.CUSTOM, base_url=url)
                with self.assertRaises(ValidationError) as ctx:
                    provider.clean()
                self.assertEqual(ctx.exception.message_dict, {"base_url": [message]})

    def test_enabled_needs_key(self):
        with self.assertRaises(ValidationError) as ctx:
            LLMProviderConfig(name="A", is_enabled=True).clean()
        self.assertEqual(ctx.exception.message_dict, {"is_enabled": [DISABLED_NEEDS_KEY]})
        LLMProviderConfig(name="A", is_enabled=True, key_secret_ref="arn", key_version_id="v").clean()

    def test_timeout_range(self):
        for value in (5, 120, 600):
            LLMProviderConfig(name="A", request_timeout_seconds=value).clean()
        for value in (0, None, 4, 601):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as ctx:
                    LLMProviderConfig(name="A", request_timeout_seconds=value).clean()
                self.assertEqual(
                    ctx.exception.message_dict, {"request_timeout_seconds": ["Must be between 5 and 600 seconds."]}
                )

    def test_context_window_limit(self):
        LLMProviderConfig(name="A", context_window_tokens=10_000_000).clean()
        LLMProviderConfig(name="A", context_window_tokens=None).clean()
        with self.assertRaises(ValidationError) as ctx:
            LLMProviderConfig(name="A", context_window_tokens=10_000_001).clean()
        self.assertEqual(ctx.exception.message_dict, {"context_window_tokens": ["Must be at most 10,000,000."]})

    def test_errors_are_collected_together(self):
        provider = LLMProviderConfig(
            name="A", preset=Preset.CUSTOM, base_url="", is_enabled=True, request_timeout_seconds=1
        )
        with self.assertRaises(ValidationError) as ctx:
            provider.clean()
        self.assertEqual(set(ctx.exception.message_dict), {"base_url", "is_enabled", "request_timeout_seconds"})


class LLMProviderSaveTests(TestCase):
    def setUp(self):
        cache.clear()

    def assert_key_kept(self, provider, enabled=True):
        provider.refresh_from_db()
        self.assertTrue(provider.key_configured)
        self.assertEqual(provider.key_hint, "abcd")
        self.assertIsNotNone(provider.key_installed_at)
        self.assertEqual(provider.is_enabled, enabled)

    def assert_key_reset(self, provider):
        for instance in (provider, LLMProviderConfig.objects.get(pk=provider.pk)):
            self.assertEqual(tuple(getattr(instance, f) for f in KEY_FIELDS), ("", "", ""))
            self.assertIsNone(instance.key_installed_at)
            self.assertFalse(instance.is_enabled)

    def test_create_keeps_key_fields(self):
        self.assert_key_kept(make_keyed_provider())

    def test_unrelated_change_keeps_key(self):
        provider = make_keyed_provider()
        provider.name = "Renamed"
        provider.request_timeout_seconds = 30
        provider.save()
        self.assert_key_kept(provider)

    def test_each_endpoint_change_resets_key(self):
        changes = ({"preset": Preset.MOONSHOT}, {"api_format": "anthropic"}, {"base_url": "https://gw.example.com"})
        for index, change in enumerate(changes):
            with self.subTest(change=change):
                provider = make_keyed_provider(name=f"P{index}", preset=Preset.CUSTOM, base_url="https://a.example.com")
                for field, value in change.items():
                    setattr(provider, field, value)
                provider.save()
                self.assert_key_reset(provider)

    def test_update_fields_path_adds_reset_fields(self):
        provider = make_keyed_provider()
        provider.preset = Preset.OPENAI
        provider.save(update_fields=["preset"])
        self.assert_key_reset(provider)
        self.assertEqual(LLMProviderConfig.objects.get(pk=provider.pk).preset, Preset.OPENAI)

    def test_update_fields_without_endpoint_change_is_untouched(self):
        provider = make_keyed_provider()
        provider.name = "Renamed"
        provider.is_enabled = False  # not in update_fields, so it must not be written
        provider.save(update_fields=["name"])
        self.assert_key_kept(provider, enabled=True)
        self.assertEqual(provider.name, "Renamed")

    def test_without_key_endpoint_change_does_not_query_or_reset(self):
        provider = make_provider(is_enabled=True)
        provider.preset = Preset.OPENAI
        with self.assertNumQueries(1):
            provider.save(update_fields=["preset"])
        provider.refresh_from_db()
        self.assertTrue(provider.is_enabled)

    def test_missing_row_is_saved_without_reset(self):
        provider = make_keyed_provider()
        LLMProviderConfig.objects.filter(pk=provider.pk).delete()
        provider.preset = Preset.OPENAI
        provider.save()
        self.assert_key_kept(provider)

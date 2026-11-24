from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.services.credential_store import get_store, memory, version_token_for
from apps.system_intelligence.services.agents.providers.keys import (
    KEY_FORMAT,
    KEY_NAME,
    MAX_KEY_CHARS,
    MISMATCH,
    NOT_INSTALLED,
    UNREADABLE,
    ProviderKeyError,
    install_api_key,
    read_api_key,
    remove_api_key,
    validate_api_key,
)

from . import make_provider

API_KEY = "fake-fake-fake-cdef"


@override_settings(CREDENTIAL_STORE_BACKEND="memory", CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER=False)
class ProviderKeyTests(TestCase):
    def setUp(self):
        cache.clear()
        memory.reset()
        self.addCleanup(memory.reset)
        self.provider = make_provider()

    def test_validate_api_key_strips_and_accepts_printable_ascii(self):
        self.assertEqual(validate_api_key(f"  {API_KEY}\n"), API_KEY)
        self.assertEqual(validate_api_key("a" * MAX_KEY_CHARS), "a" * MAX_KEY_CHARS)
        self.assertEqual(validate_api_key("!~" * 4), "!~" * 4)

    def test_validate_api_key_rejects_bad_formats(self):
        for value in (
            None,
            12345678,
            "",
            "short",
            "a" * (MAX_KEY_CHARS + 1),
            "sk-has space",
            "sk-tab\tkey",
            "sk-ключ-123",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ProviderKeyError) as ctx:
                    validate_api_key(value)
                self.assertEqual(str(ctx.exception), KEY_FORMAT)

    def test_install_pins_version_and_read_returns_key(self):
        install_api_key(self.provider, f" {API_KEY} ")

        self.provider.refresh_from_db()
        self.assertTrue(self.provider.key_configured)
        self.assertTrue(self.provider.key_secret_ref.startswith("memory:"))
        self.assertEqual(self.provider.key_hint, API_KEY[-4:])
        self.assertIsNotNone(self.provider.key_installed_at)
        self.assertEqual(read_api_key(self.provider), API_KEY)
        payload = get_store().read(KEY_NAME, arn=self.provider.key_secret_ref, version_id=self.provider.key_version_id)
        self.assertEqual(payload, {"provider_id": str(self.provider.pk), "api_key": API_KEY})

    def test_reinstalling_the_same_key_is_idempotent(self):
        install_api_key(self.provider, API_KEY)
        first_version = self.provider.key_version_id

        install_api_key(self.provider, API_KEY)

        self.provider.refresh_from_db()
        self.assertEqual(self.provider.key_version_id, first_version)
        self.assertEqual(read_api_key(self.provider), API_KEY)
        self.assertEqual(len(get_store().describe(KEY_NAME).version_stages), 1)

    def test_installing_a_new_key_pins_a_new_version(self):
        install_api_key(self.provider, API_KEY)
        first_version = self.provider.key_version_id

        install_api_key(self.provider, "sk-second-key-9999")

        self.provider.refresh_from_db()
        self.assertNotEqual(self.provider.key_version_id, first_version)
        self.assertEqual(self.provider.key_hint, "9999")
        self.assertEqual(read_api_key(self.provider), "sk-second-key-9999")

    def test_same_key_on_two_providers_gets_distinct_versions(self):
        other = make_provider(name="Other")
        install_api_key(self.provider, API_KEY)
        install_api_key(other, API_KEY)
        self.assertNotEqual(self.provider.key_version_id, other.key_version_id)

    def test_install_rejects_bad_key_without_touching_the_store(self):
        with self.assertRaisesMessage(ProviderKeyError, KEY_FORMAT):
            install_api_key(self.provider, "short")
        self.provider.refresh_from_db()
        self.assertFalse(self.provider.key_configured)
        self.assertEqual(get_store().describe(KEY_NAME).version_stages, ())

    def test_install_store_failure_is_wrapped_without_the_key(self):
        with override_settings(CREDENTIAL_STORE_BACKEND="no-such-backend"):
            with self.assertRaises(ProviderKeyError) as ctx:
                install_api_key(self.provider, API_KEY)
        message = str(ctx.exception)
        self.assertTrue(message.startswith("The API key could not be stored: "))
        self.assertNotIn(API_KEY, message)
        self.assertIsNone(ctx.exception.__cause__)
        self.provider.refresh_from_db()
        self.assertFalse(self.provider.key_configured)

    def test_read_without_key_is_not_installed(self):
        with self.assertRaisesMessage(ProviderKeyError, NOT_INSTALLED):
            read_api_key(self.provider)
        self.provider.key_secret_ref = "memory:x"
        with self.assertRaisesMessage(ProviderKeyError, NOT_INSTALLED):
            read_api_key(self.provider)

    def test_read_of_missing_version_or_foreign_reference_is_unreadable(self):
        install_api_key(self.provider, API_KEY)
        memory.reset()
        with self.assertRaisesMessage(ProviderKeyError, UNREADABLE):
            read_api_key(self.provider)

        install_api_key(self.provider, API_KEY)
        self.provider.key_secret_ref = "memory:itg/backend/gmail-api/service-account-key"
        with self.assertRaisesMessage(ProviderKeyError, UNREADABLE):
            read_api_key(self.provider)

    def test_read_refuses_a_pin_copied_to_another_provider(self):
        install_api_key(self.provider, API_KEY)
        other = make_provider(
            name="Copycat", key_secret_ref=self.provider.key_secret_ref, key_version_id=self.provider.key_version_id
        )
        with self.assertRaises(ProviderKeyError) as ctx:
            read_api_key(other)
        self.assertEqual(str(ctx.exception), MISMATCH)

    def test_read_refuses_payload_without_a_usable_key(self):
        own_id = str(self.provider.pk)
        payloads = (
            {"provider_id": own_id},
            {"provider_id": own_id, "api_key": 123},
            {"provider_id": own_id, "api_key": "   "},
            {"api_key": API_KEY},
        )
        for index, payload in enumerate(payloads):
            with self.subTest(payload=payload):
                stored = get_store().put(KEY_NAME, payload, version_token=version_token_for(KEY_NAME, f"bad-{index}"))
                self.provider.key_secret_ref = stored.arn
                self.provider.key_version_id = stored.version_id
                with self.assertRaisesMessage(ProviderKeyError, MISMATCH):
                    read_api_key(self.provider)

    def test_remove_unpins_and_disables_but_keeps_the_stored_version(self):
        install_api_key(self.provider, API_KEY)
        self.provider.is_enabled = True
        self.provider.save(update_fields=["is_enabled"])
        version_id = self.provider.key_version_id

        remove_api_key(self.provider)

        self.provider.refresh_from_db()
        self.assertFalse(self.provider.key_configured)
        self.assertEqual(
            (self.provider.key_secret_ref, self.provider.key_version_id, self.provider.key_hint), ("", "", "")
        )
        self.assertIsNone(self.provider.key_installed_at)
        self.assertFalse(self.provider.is_enabled)
        self.assertIn(version_id, dict(get_store().describe(KEY_NAME).version_stages))

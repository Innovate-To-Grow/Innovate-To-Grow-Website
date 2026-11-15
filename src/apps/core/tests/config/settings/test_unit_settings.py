"""Check the unit-test speed setting stays isolated from integration settings."""

from django.conf import global_settings
from django.contrib.auth.hashers import PBKDF2PasswordHasher, check_password, make_password
from django.test import SimpleTestCase, override_settings

from config.settings.environments import test as integration_settings
from config.settings.environments import unit as unit_settings


@override_settings(PASSWORD_HASHERS=unit_settings.PASSWORD_HASHERS)
class UnitPasswordSettingsTests(SimpleTestCase):
    def test_unit_passwords_use_the_fast_hasher_and_verify(self):
        encoded = make_password("unit-only")
        self.assertTrue(encoded.startswith("md5$"))
        self.assertTrue(check_password("unit-only", encoded))
        self.assertFalse(check_password("wrong-unit-value", encoded))

    def test_existing_strong_password_fixtures_still_verify(self):
        encoded = PBKDF2PasswordHasher().encode("unit-only", "fixture-salt", iterations=1000)
        self.assertTrue(check_password("unit-only", encoded))
        self.assertFalse(check_password("wrong-unit-value", encoded))

    def test_integration_and_default_profiles_keep_strong_hashers(self):
        fast = "django.contrib.auth.hashers.MD5PasswordHasher"
        hashers = getattr(integration_settings, "PASSWORD_HASHERS", global_settings.PASSWORD_HASHERS)
        self.assertNotIn(fast, hashers)
        self.assertNotIn(fast, global_settings.PASSWORD_HASHERS)

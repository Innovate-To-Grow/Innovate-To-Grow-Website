from django.test import SimpleTestCase

from apps.event.views.registration.phones import _validate_phone_digits


class ValidatePhoneDigitsTest(SimpleTestCase):
    def test_empty_phone_returns_none(self):
        self.assertIsNone(_validate_phone_digits("   ", "1-US"))

    def test_plus_prefixed_non_digits_rejected(self):
        self.assertEqual(
            _validate_phone_digits("+1abc", "1-US"),
            "Phone number must contain only digits.",
        )

    def test_non_plus_non_digits_rejected(self):
        self.assertEqual(
            _validate_phone_digits("12ab", "1-US"),
            "Phone number must contain only digits.",
        )

    def test_plus_country_code_stripped_then_empty_is_too_short(self):
        # "+1" -> strip "+" -> "1" -> starts with country code "1" -> stripped to "" -> too short.
        self.assertEqual(
            _validate_phone_digits("+1", "1-US"),
            "Phone number is too short (minimum 4 digits).",
        )

    def test_us_too_short_rejected(self):
        self.assertEqual(
            _validate_phone_digits("123", "1-US"),
            "US phone numbers must be exactly 10 digits.",
        )

    def test_us_too_long_rejected(self):
        self.assertEqual(
            _validate_phone_digits("1234567890123456", "1-US"),
            "US phone numbers must be exactly 10 digits.",
        )

    def test_us_valid_ten_digits_passes(self):
        self.assertIsNone(_validate_phone_digits("5551234567", "1-US"))

    def test_plus_country_code_with_valid_remainder_passes(self):
        self.assertIsNone(_validate_phone_digits("+15551234567", "1-US"))

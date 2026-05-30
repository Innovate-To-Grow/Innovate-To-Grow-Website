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

    def test_generic_region_too_short(self):
        self.assertEqual(
            _validate_phone_digits("123", "44"),
            "Phone number is too short (minimum 4 digits).",
        )

    def test_generic_region_too_long(self):
        self.assertEqual(
            _validate_phone_digits("1234567890123456", "44"),
            "Phone number is too long (maximum 15 digits).",
        )

    def test_generic_region_valid_length_passes(self):
        self.assertIsNone(_validate_phone_digits("1234567", "44"))

    def test_us_valid_ten_digits_passes(self):
        self.assertIsNone(_validate_phone_digits("5551234567", "1-US"))

    def test_china_valid_eleven_digits_passes(self):
        self.assertIsNone(_validate_phone_digits("13812345678", "86"))

    def test_plus_country_code_with_valid_remainder_passes(self):
        self.assertIsNone(_validate_phone_digits("+15551234567", "1-US"))

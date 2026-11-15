import time
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.tokens import (
    ALLOWED_TOKEN_FUNCTIONS,
    MAX_TOKEN_VALUE_LENGTH,
    coerce_token_value,
    is_safe_token_key,
    is_safe_token_value,
)
from apps.cms.tests.services.theme.test_style_tokens import ACCEPTED_TOKEN_VALUES, REFUSED_TOKEN_VALUES


class IsSafeTokenKeyTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_lowercase_digits_and_underscores_are_safe(self):
        for key in ("primary", "font_size_h1", "h2", "a_b_c_1"):
            with self.subTest(key=key):
                self.assertTrue(is_safe_token_key(key))

    def test_other_keys_are_rejected(self):
        for key in ("Primary", "a-b", "a;b", "a b", "", "a}b", "ü", 1, None, ("a",)):
            with self.subTest(key=key):
                self.assertFalse(is_safe_token_key(key))


class CoerceTokenValueTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_strings_are_stripped(self):
        self.assertEqual(coerce_token_value("  #fff  "), "#fff")

    def test_numbers_are_stringified(self):
        self.assertEqual(coerce_token_value(0), "0")
        self.assertEqual(coerce_token_value(12), "12")
        self.assertEqual(coerce_token_value(1.5), "1.5")

    def test_none_bool_and_containers_are_skipped(self):
        for value in (None, True, False, {"a": "b"}, ["1px"], ("1px",)):
            with self.subTest(value=value):
                self.assertIsNone(coerce_token_value(value))

    def test_empty_and_blank_strings_are_skipped(self):
        self.assertIsNone(coerce_token_value(""))
        self.assertIsNone(coerce_token_value("   "))

    def test_forbidden_patterns_are_rejected(self):
        for value in (
            "red; color: blue",
            "red { x",
            "red } body",
            "<script>",
            "a > b",
            "1px /* c */",
            "url(https://example.com/x.png)",
            "URL(https://example.com/x.png)",
            "expression(alert(1))",
            "ExPrEsSiOn(alert(1))",
        ):
            with self.subTest(value=value):
                self.assertIsNone(coerce_token_value(value))

    def test_length_limit(self):
        self.assertEqual(coerce_token_value("a" * MAX_TOKEN_VALUE_LENGTH), "a" * MAX_TOKEN_VALUE_LENGTH)
        self.assertIsNone(coerce_token_value("a" * (MAX_TOKEN_VALUE_LENGTH + 1)))

    def test_ordinary_css_values_are_kept(self):
        for value in ("0 2px 8px rgba(15, 45, 82, 0.12)", "'Open Sans', Arial, sans-serif", "calc(100% - 2rem)"):
            with self.subTest(value=value):
                self.assertEqual(coerce_token_value(value), value)


class IsSafeTokenValueTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_refused_values(self):
        for reason, values in REFUSED_TOKEN_VALUES.items():
            for value in values:
                with self.subTest(reason=reason, value=value[:60]):
                    self.assertFalse(is_safe_token_value(value))
                    self.assertIsNone(coerce_token_value(value))

    def test_accepted_values(self):
        for reason, values in ACCEPTED_TOKEN_VALUES.items():
            for value in values:
                with self.subTest(reason=reason, value=value[:60]):
                    self.assertTrue(is_safe_token_value(value))
                    self.assertEqual(coerce_token_value(value), value)

    def test_every_allowed_function_is_accepted_in_any_case(self):
        for name in sorted(ALLOWED_TOKEN_FUNCTIONS):
            for spelled in (name, name.upper()):
                with self.subTest(function=spelled):
                    self.assertTrue(is_safe_token_value(f"{spelled}(1px)"))

    def test_allowed_function_list_has_no_loading_function(self):
        self.assertTrue(
            {"url", "image-set", "-webkit-image-set", "src", "image", "attr", "env"}.isdisjoint(ALLOWED_TOKEN_FUNCTIONS)
        )

    def test_empty_value_is_refused(self):
        self.assertFalse(is_safe_token_value(""))

    def test_every_control_character_is_refused(self):
        for code in [*range(0x00, 0x20), *range(0x7F, 0xA0)]:
            with self.subTest(code=hex(code)):
                self.assertFalse(is_safe_token_value(f"red{chr(code)}blue"))

    def test_every_lone_surrogate_is_refused(self):
        for code in (0xD800, 0xDBFF, 0xDC00, 0xDFFF):
            with self.subTest(code=hex(code)):
                self.assertFalse(is_safe_token_value(f"#fff{chr(code)}"))
                self.assertIsNone(coerce_token_value(f"#fff{chr(code)}"))

    def test_leading_or_trailing_tab_is_stripped_before_the_check(self):
        # coerce_token_value strips surrounding whitespace first; only an inner tab reaches the check.
        self.assertFalse(is_safe_token_value("\t#fff"))
        self.assertEqual(coerce_token_value("\t#fff\t"), "#fff")
        self.assertIsNone(coerce_token_value("#fff\t#000"))

    def test_surrounding_whitespace_is_stripped_before_the_check(self):
        # A trailing line break is stripped away; one inside the value is still refused.
        self.assertEqual(coerce_token_value("  #fff\n"), "#fff")
        self.assertIsNone(coerce_token_value("#fff\n#000"))
        self.assertEqual(coerce_token_value(" " + "a" * MAX_TOKEN_VALUE_LENGTH + " "), "a" * MAX_TOKEN_VALUE_LENGTH)


class FunctionScanTimeTests(SimpleTestCase):
    """The function-name scan stays linear on long names (CodeQL alert #655, py/polynomial-redos).

    The length cap is lifted so the values reach the scan: a quadratic scan spends about 20 seconds
    on one of these values, the linear one milliseconds.
    """

    SIZE = 50_000
    TIME_LIMIT_SECONDS = 2.0

    def setUp(self):
        cache.clear()
        patcher = mock.patch("apps.cms.services.styles.tokens.MAX_TOKEN_VALUE_LENGTH", 4 * self.SIZE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_checked_quickly(self, value, expected):
        start = time.perf_counter()
        self.assertIs(is_safe_token_value(value), expected)
        self.assertLess(time.perf_counter() - start, self.TIME_LIMIT_SECONDS)

    def test_long_names_without_a_call_are_accepted_quickly(self):
        n = self.SIZE
        for value in (
            "A" * n,
            "rgb" + "A" * n,
            "a-" * n,
            "a1" * n,
            "A" * n + " " * n + "x",
            f"var(--{'a' * n})",
        ):
            with self.subTest(value=value[:20], length=len(value)):
                self.assert_checked_quickly(value, True)

    def test_forbidden_call_after_a_long_name_is_still_refused_quickly(self):
        n = self.SIZE
        for value in ("A" * n + "(1)", "A" * n + " url(x)", "a-" * n + " attr(x)", "A" * n + " " * n + "(1)"):
            with self.subTest(value=value[:20], length=len(value)):
                self.assert_checked_quickly(value, False)

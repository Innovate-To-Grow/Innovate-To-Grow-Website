"""Tests for ``apps.cms.services.styles.tokens`` (design tokens rendered as ``--itg-*`` properties)."""

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.models.content.layout.site_settings import default_design_tokens
from apps.cms.services.styles.tokens import (
    ALLOWED_TOKEN_FUNCTIONS,
    MAX_TOKEN_VALUE_LENGTH,
    TOKEN_GROUP_PREFIX,
    coerce_token_value,
    is_safe_token_key,
    is_safe_token_value,
    render_tokens_css,
    token_variable_name,
)

LOGGER = "apps.cms.services.styles.tokens"


def _declarations(css):
    """The ``--itg-*`` declaration lines of a rendered ``:root`` block."""
    return [line.strip() for line in css.splitlines() if line.strip().startswith("--itg-")]


class TokenVariableNameTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_colors_group_gets_color_prefix(self):
        self.assertEqual(token_variable_name("colors", "primary_hover"), "--itg-color-primary-hover")

    def test_other_known_groups_get_no_prefix(self):
        for group in TOKEN_GROUP_PREFIX:
            if group == "colors":
                continue
            with self.subTest(group=group):
                self.assertEqual(token_variable_name(group, "font_size_h1"), "--itg-font-size-h1")

    def test_unknown_group_gets_no_prefix(self):
        self.assertEqual(token_variable_name("spacing", "gap_lg"), "--itg-gap-lg")


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


# Values refused by ``is_safe_token_value``, grouped by the rule that refuses them.
REFUSED_TOKEN_VALUES = {
    "backslash (CSS escape)": (
        "\\75 rl(https://example.com/x.png)",
        "\\72 ed",
        "re\\d",
        "red\\",
        "'Open Sans\\'",
    ),
    "line break or form feed": ("red\nblue", "red\rblue", "red\r\nblue", "red\fblue"),
    "other control character": (
        "red\tblue",
        "1px\t2px",
        "re\x00d",
        "red\x00",
        "\x00",
        "red\x01blue",
        "red\x0bblue",
        "red\x1bblue",
        "red\x7fblue",
        "red\x85blue",
        "red\x9fblue",
    ),
    # A lone surrogate cannot be encoded as UTF-8, so serving it would fail the whole stylesheet.
    "lone surrogate": ("red\ud800", "\udfff", "re\udc00d", "'Open Sans\ud83d'"),
    "rule or tag delimiter": ("red; color: blue", "red {", "red }", "a<b", "a>b"),
    "semicolon inside quotes": ("'a;b'", '"Open Sans;", serif'),
    "comment": ("1px /* c */", "/*", "'/*'"),
    "unbalanced bracket": (
        "rgba(0, 0, 0",
        "calc((1px + 2px)",
        "[x",
        "0 2px)",
        "x]",
        "([)]",
        "(]",
        ")(",
        "1px) rgba(0, 0, 0, 1) (",
        "]x[",
    ),
    "unclosed quote": ("'Open Sans", '"Open Sans', "'Open Sans', \"Arial", "it's"),
    "function that loads or reads something": (
        "url(https://example.com/x.png)",
        "URL(https://example.com/x.png)",
        "Url(x)",
        "url (x)",
        "image-set('a.png' 1x)",
        "IMAGE-SET('a.png' 1x)",
        "-webkit-image-set('a.png' 1x)",
        "src(x)",
        "image(x)",
        "cross-fade(a, b)",
        "element(#x)",
        "attr(data-x)",
        "env(safe-area-inset-top)",
        "expression(alert(1))",
    ),
    "unknown function": ("foo()", "foo(1)", "-webkit-linear-gradient(red, blue)", "scaleX(2)", "--x(1)", "red (1)"),
    "forbidden function nested in an allowed one": (
        "var(--x, url(a.png))",
        "calc(1px + attr(x))",
        "linear-gradient(red, blue), url(a.png)",
    ),
    "too long": ("a" * (MAX_TOKEN_VALUE_LENGTH + 1), "rgba(0, 0, 0, 0.5) " * 11),
}

ACCEPTED_TOKEN_VALUES = {
    "font stack": (
        "'Open Sans', Arial, sans-serif",
        '"Helvetica Neue", Helvetica, Arial, sans-serif',
        '"Kid\'s Font", \'Say "hi"\', serif',
        "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    ),
    "shadow": (
        "0 2px 8px rgba(15, 45, 82, 0.12)",
        "0 1px 2px rgba(0, 0, 0, 0.1), 0 4px 8px hsla(0, 0%, 0%, 0.2)",
        "inset 0 0 0 1px hsl(210 50% 40% / 0.2)",
    ),
    "maths and references": (
        "calc(100% - 2rem)",
        "calc(var(--itg-gap) * 2)",
        "var(--itg-color-primary)",
        "var(--itg-gap, 1rem)",
        "clamp(1rem, 2vw + 0.5rem, 3rem)",
        "min(100%, 1170px)",
        "max(50vh, calc((100% - 2rem) / 3))",
    ),
    "colour": (
        "#0f2d52",
        "transparent",
        "rgb(0 0 0 / 50%)",
        "RGBA(0, 0, 0, 0.5)",
        "color-mix(in srgb, #0f2d52 80%, white)",
        "oklch(70% 0.1 250)",
    ),
    "gradient": (
        "linear-gradient(90deg, #fff 0%, rgb(0 0 0 / 50%) 100%)",
        "radial-gradient(circle at top, #fff, transparent)",
        "repeating-linear-gradient(45deg, #000 0 10px, #fff 10px 20px)",
    ),
    "timing, transform and grid": (
        "cubic-bezier(0.4, 0, 0.2, 1)",
        "steps(4, end)",
        "translateY(-2px)",
        "translateX(2px) rotate(45deg) scale(1.05)",
        "repeat(auto-fit, minmax(240px, 1fr))",
        "fit-content(20rem)",
    ),
    "brackets and function names inside quotes": (
        "'Open Sans (Bold)', serif",
        "'['",
        '")"',
        # A quoted "url(" is a string, not a call, so nothing is loaded.
        "'url(x)'",
    ),
    "length limit": ("a" * MAX_TOKEN_VALUE_LENGTH,),
    "non-ASCII text": (
        "'Noto Sans JP', '\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4 ProN', sans-serif",
        "'\u00dcn\u00efc\u00f6d\u00e9 Sans'",
        # An astral character is one code point in Python, not a surrogate pair.
        "'Fira Sans \U0001f600'",
    ),
}


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


class RenderTokensCssTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_renders_root_block_with_prefixes(self):
        css = render_tokens_css(
            {
                "colors": {"primary": "#0f2d52"},
                "typography": {"font_size_h1": "2.25rem"},
                "layout": {"page_max_width": "1170px"},
            }
        )

        self.assertEqual(
            css,
            ":root {\n"
            "  --itg-color-primary: #0f2d52;\n"
            "  --itg-font-size-h1: 2.25rem;\n"
            "  --itg-page-max-width: 1170px;\n"
            "}\n",
        )

    def test_numbers_are_rendered_as_text(self):
        css = render_tokens_css({"typography": {"line_height_body": 1.5, "weight": 700}})

        self.assertIn("  --itg-line-height-body: 1.5;", css)
        self.assertIn("  --itg-weight: 700;", css)

    def test_unknown_group_renders_without_prefix_and_warns(self):
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            css = render_tokens_css({"spacing": {"gap_lg": "2rem"}})

        self.assertIn("  --itg-gap-lg: 2rem;", css)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("'spacing' is not a known group", logs.output[0])

    def test_none_bool_dict_and_list_values_are_skipped_with_warnings(self):
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            css = render_tokens_css(
                {
                    "colors": {
                        "primary": "#fff",
                        "nothing": None,
                        "flag": True,
                        "nested": {"a": "b"},
                        "listed": ["#000"],
                    }
                }
            )

        self.assertEqual(_declarations(css), ["--itg-color-primary: #fff;"])
        self.assertEqual(len(logs.records), 4)
        for name in ("nothing", "flag", "nested", "listed"):
            with self.subTest(name=name):
                self.assertTrue(any(f"'{name}' skipped: unsafe or non-text value" in line for line in logs.output))

    def test_each_forbidden_value_is_skipped_with_a_warning(self):
        for value in (
            "red; } body { display:none",
            "red {",
            "red }",
            "<style>",
            "a>b",
            "1px /* x",
            "url(https://example.com/a.png)",
            "Url(https://example.com/a.png)",
            "expression(alert(1))",
            "EXPRESSION(alert(1))",
            "a" * (MAX_TOKEN_VALUE_LENGTH + 1),
            "\\75 rl(https://example.com/a.png)",
            "red\\",
            "red\nblue",
            "red\rblue",
            "red\fblue",
            "'a;b'",
            "rgba(0, 0, 0",
            "x]",
            "'Open Sans",
            '"Open Sans',
            "image-set('a.png' 1x)",
            "-webkit-image-set('a.png' 1x)",
            "src(https://example.com/a.png)",
            "foo(1)",
            "1px) (",
        ):
            with self.subTest(value=value[:40]):
                with self.assertLogs(LOGGER, level="WARNING") as logs:
                    css = render_tokens_css({"colors": {"primary": value, "secondary": "#005487"}})

                self.assertEqual(_declarations(css), ["--itg-color-secondary: #005487;"])
                self.assertNotIn(value, css)
                self.assertEqual(len(logs.records), 1)
                self.assertIn("'primary' skipped: unsafe or non-text value", logs.output[0])

    def test_control_characters_and_surrogates_are_skipped_and_the_rest_renders(self):
        tokens = {
            "colors": {"primary": "red\tblue", "secondary": "#005487", "accent": "\x00"},
            "typography": {"font_family_body": "'Open Sans\ud800'", "font_size_h1": "2rem"},
        }

        with self.assertLogs(LOGGER, level="WARNING") as logs:
            css = render_tokens_css(tokens)

        self.assertEqual(css, ":root {\n  --itg-color-secondary: #005487;\n  --itg-font-size-h1: 2rem;\n}\n")
        css.encode("utf-8")  # Nothing left that cannot be served.
        self.assertEqual(len(logs.records), 3)
        for name in ("primary", "accent", "font_family_body"):
            with self.subTest(name=name):
                self.assertTrue(any(f"'{name}' skipped: unsafe or non-text value" in line for line in logs.output))

    def test_bad_keys_are_skipped_with_a_warning(self):
        for key in ("Primary", "a-b", "a;b", 7):
            with self.subTest(key=key):
                with self.assertLogs(LOGGER, level="WARNING") as logs:
                    css = render_tokens_css({"colors": {key: "#fff", "secondary": "#000"}})

                self.assertEqual(_declarations(css), ["--itg-color-secondary: #000;"])
                self.assertEqual(len(logs.records), 1)
                self.assertIn("keys must match [a-z0-9_]+", logs.output[0])

    def test_returns_empty_string_when_nothing_is_usable(self):
        with self.assertLogs(LOGGER, level="WARNING"):
            self.assertEqual(render_tokens_css({"colors": {"primary": "red; x", "Bad": "#fff"}}), "")
        self.assertEqual(render_tokens_css({}), "")
        self.assertEqual(render_tokens_css({"colors": {}}), "")

    def test_non_dict_input_and_groups_render_nothing(self):
        self.assertEqual(render_tokens_css(None), "")
        self.assertEqual(render_tokens_css("colors"), "")
        self.assertEqual(render_tokens_css([{"colors": {"primary": "#fff"}}]), "")
        with self.assertNoLogs(LOGGER, level="WARNING"):
            # Non-dict groups are skipped before the unknown-group check, so they log nothing.
            self.assertEqual(render_tokens_css({"colors": "#fff", "mystery": 5}), "")

    def test_every_default_design_token_renders(self):
        tokens = default_design_tokens()
        expected = sum(len(values) for values in tokens.values())

        with self.assertNoLogs(LOGGER, level="WARNING"):
            css = render_tokens_css(tokens)

        self.assertEqual(len(_declarations(css)), expected)
        self.assertTrue(css.startswith(":root {\n"))
        self.assertTrue(css.endswith("\n}\n"))
        for group, values in tokens.items():
            for key, value in values.items():
                with self.subTest(group=group, key=key):
                    self.assertIn(f"  {token_variable_name(group, key)}: {value};", css)

    def test_unbalanced_brackets_are_rejected(self):
        # An unclosed "(" or "[" would swallow the closing "}" of :root and every rule after it.
        for value in ("0 2px rgba(0, 0, 0", "[x"):
            with self.subTest(value=value):
                with self.assertLogs(LOGGER, level="WARNING"):
                    css = render_tokens_css({"effects": {"shadow_card_hover": value}, "colors": {"primary": "#fff"}})
                self.assertEqual(_declarations(css), ["--itg-color-primary: #fff;"])

    def test_unterminated_string_is_rejected(self):
        # An unclosed quote would run to the end of the line and merge the next token into this one.
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            css = render_tokens_css({"typography": {"font_family_body": "'Open Sans", "font_size_h1": "2rem"}})
        self.assertEqual(_declarations(css), ["--itg-font-size-h1: 2rem;"])
        self.assertIn("'font_family_body' skipped: unsafe or non-text value", logs.output[0])

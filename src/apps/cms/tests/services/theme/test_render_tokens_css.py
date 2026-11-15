from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.models.content.layout.site_settings import default_design_tokens
from apps.cms.services.styles.tokens import (
    MAX_TOKEN_VALUE_LENGTH,
    render_tokens_css,
    token_variable_name,
)
from apps.cms.tests.services.theme.test_style_tokens import LOGGER, _declarations


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

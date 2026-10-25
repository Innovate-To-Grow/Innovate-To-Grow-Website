import re
from pathlib import Path

from django.test import SimpleTestCase

from apps.cms.services.styles.theme import LAYER_ORDER_STATEMENT, build_theme_css, theme_etag

LAYERS_CSS = Path(__file__).resolve().parents[5] / "pages" / "src" / "styles" / "layers.css"


class Settings:
    def __init__(self, design_tokens=None, custom_css=""):
        self.design_tokens = design_tokens or {}
        self.custom_css = custom_css


class BuildThemeCssTests(SimpleTestCase):
    def test_the_layer_order_matches_the_frontend(self):
        statement = re.search(r"@layer\s+[\w.\s,-]+;", LAYERS_CSS.read_text(encoding="utf-8")).group(0)
        self.assertEqual(" ".join(statement.split()), LAYER_ORDER_STATEMENT)

    def test_opens_with_the_layer_order_then_tokens_then_custom_css(self):
        css = build_theme_css(Settings({"colors": {"primary": "#123456"}}, ".site-header { color: red; }"))

        self.assertEqual(
            css,
            f"{LAYER_ORDER_STATEMENT}\n\n"
            "@layer itg.tokens {\n:root {\n  --itg-color-primary: #123456;\n}\n}\n\n"
            "@layer itg.overrides {\n.site-header { color: red; }\n}\n",
        )

    def test_leaves_out_empty_parts(self):
        self.assertEqual(build_theme_css(Settings({}, "  \n")), f"{LAYER_ORDER_STATEMENT}\n")

    def test_unsafe_token_values_stay_out(self):
        css = build_theme_css(Settings({"colors": {"primary": "red;} body{display:none"}}))
        self.assertNotIn("display:none", css)

    def test_etag_follows_the_body(self):
        self.assertEqual(theme_etag("a"), theme_etag("a"))
        self.assertNotEqual(theme_etag("a"), theme_etag("b"))
        self.assertRegex(theme_etag("a"), r'^"[0-9a-f]{32}"$')

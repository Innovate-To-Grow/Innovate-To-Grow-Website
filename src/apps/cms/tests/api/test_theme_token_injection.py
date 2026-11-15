from unittest import skipUnless

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from apps.cms.models import SiteSettings
from apps.cms.services.styles.theme import LAYER_ORDER_STATEMENT


class ThemeTokenInjectionTests(TestCase):
    """Unsafe design-token keys and values never reach the served theme sheet."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def _set_tokens(self, tokens):
        settings = SiteSettings.load()
        settings.design_tokens = tokens
        settings.save()
        cache.clear()

    @staticmethod
    def _theme(tokens_css=""):
        if not tokens_css:
            return f"{LAYER_ORDER_STATEMENT}\n"
        return f"{LAYER_ORDER_STATEMENT}\n\n@layer itg.tokens {{\n{tokens_css}}}\n"

    def test_injected_value_and_key_are_left_out_of_the_theme(self):
        self._set_tokens(
            {
                "colors": {"primary": "red; } body { display:none", "secondary": "#005487"},
                "layout": {"Bad-Key;x": "1px", "page_max_width": "1170px"},
            }
        )

        with self.assertLogs("apps.cms.services.styles.tokens", level="WARNING") as logs:
            resp = self.client.get("/layout/theme.css")

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn("display:none", body)
        self.assertNotIn("Bad-Key", body)
        self.assertNotIn("bad-key", body)
        self.assertEqual(
            body, self._theme(":root {\n  --itg-color-secondary: #005487;\n  --itg-page-max-width: 1170px;\n}\n")
        )
        self.assertEqual(len(logs.records), 2)

    def test_only_unsafe_tokens_leave_just_the_layer_order(self):
        self._set_tokens({"colors": {"primary": "url(https://example.com/x)"}})

        with self.assertLogs("apps.cms.services.styles.tokens", level="WARNING"):
            body = self.client.get("/layout/theme.css").content.decode()

        self.assertEqual(body, self._theme())

    def test_control_character_tokens_are_left_out_of_the_theme(self):
        # BEL, not NUL: PostgreSQL jsonb refuses to store \u0000 at all.
        self._set_tokens({"colors": {"primary": "red\tblue", "secondary": "#005487", "accent": "#fff\x07"}})

        with self.assertLogs("apps.cms.services.styles.tokens", level="WARNING") as logs:
            resp = self.client.get("/layout/theme.css")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode(), self._theme(":root {\n  --itg-color-secondary: #005487;\n}\n"))
        self.assertEqual(len(logs.records), 2)

    # PostgreSQL jsonb refuses a lone surrogate at save time; SQLite stores the escaped JSON text,
    # so the value comes back as a Python str that cannot be encoded as UTF-8.
    @skipUnless(connection.vendor == "sqlite", "only SQLite can store a lone surrogate in a JSONField")
    def test_stored_surrogate_token_does_not_break_the_theme(self):
        self._set_tokens(
            {
                "colors": {"primary": "#0f2d52\ud800", "secondary": "#005487"},
                "typography": {"font_family_body": "'Open Sans\udfff', serif", "font_size_h1": "2.25rem"},
            }
        )
        self.assertEqual(SiteSettings.load().design_tokens["colors"]["primary"], "#0f2d52\ud800")

        with self.assertLogs("apps.cms.services.styles.tokens", level="WARNING") as logs:
            resp = self.client.get("/layout/theme.css")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.content.decode("utf-8"),
            self._theme(":root {\n  --itg-color-secondary: #005487;\n  --itg-font-size-h1: 2.25rem;\n}\n"),
        )
        self.assertEqual(len(logs.records), 2)

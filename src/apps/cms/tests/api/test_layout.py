"""Tests for LayoutAPIView: menu filtering, serializer logic, edge cases."""

from unittest import skipUnless

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from apps.cms.models import FooterContent, Menu, SiteSettings
from apps.cms.services.styles.theme import LAYER_ORDER_STATEMENT
from apps.cms.services.styles.tokens import render_tokens_css


class LayoutMenuFilteringTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_inactive_menu_excluded(self):
        Menu.objects.create(name="active", display_name="Active", is_active=True)
        Menu.objects.create(name="inactive", display_name="Inactive", is_active=False)

        resp = self.client.get("/layout/")
        menus = resp.json()["menus"]
        self.assertEqual(len(menus), 1)
        self.assertEqual(menus[0]["name"], "active")

    def test_menus_ordered_by_display_name(self):
        Menu.objects.create(name="zebra", display_name="Zebra Menu")
        Menu.objects.create(name="alpha", display_name="Alpha Menu")

        resp = self.client.get("/layout/")
        names = [m["display_name"] for m in resp.json()["menus"]]
        self.assertEqual(names, ["Alpha Menu", "Zebra Menu"])

    def test_no_menus_returns_empty_list(self):
        resp = self.client.get("/layout/")
        self.assertEqual(resp.json()["menus"], [])

    def test_response_contains_only_menus_and_footer(self):
        resp = self.client.get("/layout/")
        self.assertEqual(set(resp.json()), {"menus", "footer"})

    def test_etag_supports_weak_and_comma_separated_if_none_match(self):
        first = self.client.get("/layout/")
        etag = first["ETag"]

        second = self.client.get("/layout/", HTTP_IF_NONE_MATCH=f'"other", W/{etag}')

        self.assertEqual(second.status_code, 304)
        self.assertIn("public", second["Cache-Control"])

    def test_multiple_active_menus(self):
        for i in range(3):
            Menu.objects.create(name=f"menu-{i}", display_name=f"Menu {i}")

        resp = self.client.get("/layout/")
        self.assertEqual(len(resp.json()["menus"]), 3)


class MenuSerializerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_home_type_item_always_links_to_root(self):
        Menu.objects.create(
            name="with-home",
            display_name="With Home",
            items=[{"type": "home", "title": "Home", "url": "/ignored"}],
        )
        resp = self.client.get("/layout/")
        items = resp.json()["menus"][0]["items"]
        self.assertEqual(items[0]["url"], "/")

    def test_app_type_preserves_url(self):
        Menu.objects.create(
            name="app-menu",
            display_name="App Menu",
            items=[{"type": "app", "title": "News", "url": "/news"}],
        )
        resp = self.client.get("/layout/")
        items = resp.json()["menus"][0]["items"]
        self.assertEqual(items[0]["url"], "/news")

    def test_external_type_preserves_url(self):
        Menu.objects.create(
            name="ext-menu",
            display_name="External Menu",
            items=[{"type": "external", "title": "Google", "url": "https://google.com", "open_in_new_tab": True}],
        )
        resp = self.client.get("/layout/")
        item = resp.json()["menus"][0]["items"][0]
        self.assertEqual(item["url"], "https://google.com")
        self.assertTrue(item["open_in_new_tab"])

    def test_nested_children(self):
        Menu.objects.create(
            name="nested",
            display_name="Nested",
            items=[
                {
                    "type": "app",
                    "title": "Parent",
                    "url": "/parent",
                    "children": [
                        {"type": "app", "title": "Child", "url": "/child", "children": []},
                    ],
                }
            ],
        )
        resp = self.client.get("/layout/")
        parent = resp.json()["menus"][0]["items"][0]
        self.assertEqual(len(parent["children"]), 1)
        self.assertEqual(parent["children"][0]["title"], "Child")
        self.assertEqual(parent["children"][0]["children"], [])

    def test_missing_optional_fields_use_defaults(self):
        Menu.objects.create(
            name="sparse",
            display_name="Sparse",
            items=[{"title": "Minimal"}],  # missing type, url, icon, etc.
        )
        resp = self.client.get("/layout/")
        item = resp.json()["menus"][0]["items"][0]
        self.assertEqual(item["type"], "app")  # default
        self.assertEqual(item["url"], "#")  # default for non-home
        self.assertEqual(item["icon"], "")
        self.assertFalse(item["open_in_new_tab"])
        self.assertEqual(item["children"], [])

    def test_empty_items_list(self):
        Menu.objects.create(name="empty", display_name="Empty", items=[])
        resp = self.client.get("/layout/")
        self.assertEqual(resp.json()["menus"][0]["items"], [])


class LayoutFooterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_active_footer_serialized(self):
        FooterContent.objects.create(
            name="Active Footer",
            slug="active-footer",
            is_active=True,
            content={"copyright": "2026 I2G"},
        )
        resp = self.client.get("/layout/")
        footer = resp.json()["footer"]
        self.assertIsNotNone(footer)
        self.assertEqual(footer["content"]["copyright"], "2026 I2G")

    def test_no_active_footer_returns_null(self):
        resp = self.client.get("/layout/")
        self.assertIsNone(resp.json()["footer"])

    def test_inactive_footer_not_served(self):
        FooterContent.objects.create(name="Inactive", slug="inactive", is_active=False)
        resp = self.client.get("/layout/")
        self.assertIsNone(resp.json()["footer"])


class DesignTokensToCssTests(TestCase):
    """Direct unit tests for render_tokens_css edge cases."""

    def test_non_dict_tokens_returns_empty(self):
        self.assertEqual(render_tokens_css(None), "")
        self.assertEqual(render_tokens_css("not a dict"), "")
        self.assertEqual(render_tokens_css([1, 2, 3]), "")

    def test_non_dict_group_values_are_skipped(self):
        css = render_tokens_css({"layout": {"max_width": "1200px"}, "broken": "ignored"})
        self.assertIn("--itg-max-width: 1200px;", css)
        self.assertNotIn("broken", css)

    def test_all_groups_non_dict_returns_empty(self):
        self.assertEqual(render_tokens_css({"colors": "x", "layout": 5}), "")

    def test_colors_group_uses_color_prefix(self):
        css = render_tokens_css({"colors": {"primary": "#fff"}})
        self.assertIn("--itg-color-primary: #fff;", css)


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

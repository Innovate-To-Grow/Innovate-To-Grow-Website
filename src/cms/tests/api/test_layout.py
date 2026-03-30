"""Tests for LayoutAPIView: menu filtering, serializer logic, edge cases."""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from cms.models import FooterContent, Menu


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

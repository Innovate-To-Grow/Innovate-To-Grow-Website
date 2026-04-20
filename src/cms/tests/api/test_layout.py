"""Tests for LayoutAPIView: menu filtering, serializer logic, edge cases."""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from cms.models import FooterContent, Menu, SiteSettings, StyleSheet
from cms.views.views import LAYOUT_CACHE_TIMEOUT, LAYOUT_STYLESHEET_CACHE_KEY


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


class LayoutStylesheetViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_returns_text_css_content_type(self):
        resp = self.client.get("/layout/styles.css")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Type"].startswith("text/css"))

    def test_active_stylesheets_concatenated(self):
        StyleSheet.objects.create(name="a", display_name="A", css="body { color: red; }", sort_order=1)
        StyleSheet.objects.create(name="b", display_name="B", css=".x { margin: 0; }", sort_order=2)
        StyleSheet.objects.create(name="c", display_name="C", css=".never { display: none; }", is_active=False)

        resp = self.client.get("/layout/styles.css")
        body = resp.content.decode()
        self.assertIn("body { color: red; }", body)
        self.assertIn(".x { margin: 0; }", body)
        self.assertNotIn(".never", body)

    def test_design_tokens_emitted_as_css_variables(self):
        # SiteSettings.load() seeds the default design tokens on first call.
        SiteSettings.load()
        resp = self.client.get("/layout/styles.css")
        body = resp.content.decode()
        # colors group → --itg-color-* prefix
        self.assertIn("--itg-color-primary:", body)
        # typography group → no prefix
        self.assertIn("--itg-font-size-h1:", body)
        self.assertIn(":root {", body)

    def test_response_is_cached(self):
        StyleSheet.objects.create(name="cached", display_name="Cached", css="/* v1 */")
        first = self.client.get("/layout/styles.css").content.decode()
        # Mutate via raw queryset update so signals don't fire and bust the cache.
        StyleSheet.objects.filter(name="cached").update(css="/* v2 */")
        second = self.client.get("/layout/styles.css").content.decode()
        self.assertEqual(first, second)
        self.assertIn("/* v1 */", second)

    def test_save_invalidates_cache(self):
        # The invalidate signal uses transaction.on_commit(...) which is deferred
        # until the outer transaction commits. TestCase rolls its transaction
        # back for isolation, so we must capture & execute the callbacks
        # synchronously here or the cache stays stale.
        with self.captureOnCommitCallbacks(execute=True):
            sheet = StyleSheet.objects.create(name="live", display_name="Live", css="/* original */")
        self.client.get("/layout/styles.css")  # populate cache

        sheet.css = "/* updated */"
        with self.captureOnCommitCallbacks(execute=True):
            sheet.save()

        body = self.client.get("/layout/styles.css").content.decode()
        self.assertIn("/* updated */", body)
        self.assertNotIn("/* original */", body)

    def test_init_loader_css_not_in_backend_response(self):
        # The initial-load spinner now lives inline in pages/index.html so it
        # paints before this stylesheet arrives. Guard against the backend
        # re-adding it (which would duplicate the rules and break the cache-key
        # invariant documented on LAYOUT_STYLESHEET_CACHE_KEY).
        resp = self.client.get("/layout/styles.css")
        body = resp.content.decode()
        self.assertNotIn("#root:empty::before", body)
        self.assertNotIn("itg-init-loader-spin", body)

    def test_cache_control_header_enables_browser_caching(self):
        # The stylesheet is render-blocking, so browser caching is how we keep
        # the first-paint blank window short on repeat visits. Losing this
        # header would silently double first-paint time.
        resp = self.client.get("/layout/styles.css")
        cache_control = resp["Cache-Control"]
        self.assertIn("public", cache_control)
        self.assertIn(f"max-age={LAYOUT_CACHE_TIMEOUT}", cache_control)

    def test_cache_key_version_suffix_current(self):
        # The :vN suffix on the cache key is how we retire stale cached blobs
        # at deploy time when the assembled stylesheet shape changes. Pinning
        # the expected version here forces a conscious decision if someone
        # edits the assembly without bumping the key.
        self.assertTrue(
            LAYOUT_STYLESHEET_CACHE_KEY.endswith(":v3"),
            f"expected cache key to end with :v3, got {LAYOUT_STYLESHEET_CACHE_KEY}",
        )

    def test_stylesheets_emitted_in_sort_order(self):
        StyleSheet.objects.create(name="z", display_name="Z", css="/* LAST */", sort_order=99)
        StyleSheet.objects.create(name="a", display_name="A", css="/* FIRST */", sort_order=1)
        StyleSheet.objects.create(name="m", display_name="M", css="/* MIDDLE */", sort_order=50)

        body = self.client.get("/layout/styles.css").content.decode()

        self.assertLess(body.index("/* FIRST */"), body.index("/* MIDDLE */"))
        self.assertLess(body.index("/* MIDDLE */"), body.index("/* LAST */"))

    def test_empty_stylesheets_still_emits_design_tokens(self):
        # With zero StyleSheet rows the response should still be valid CSS
        # containing the design-token :root block — otherwise the inline
        # spinner in index.html falls back to its hard-coded color instead of
        # picking up the current theme.
        StyleSheet.objects.all().delete()
        SiteSettings.load()
        cache.clear()

        resp = self.client.get("/layout/styles.css")
        body = resp.content.decode()

        self.assertEqual(resp.status_code, 200)
        self.assertIn(":root {", body)
        self.assertIn("--itg-color-primary:", body)

    def test_response_populates_cache_under_expected_key(self):
        # Ties the view implementation to the public cache-key constant, so
        # the signal at cms.signals can reliably invalidate the entry.
        cache.delete(LAYOUT_STYLESHEET_CACHE_KEY)
        self.assertIsNone(cache.get(LAYOUT_STYLESHEET_CACHE_KEY))

        self.client.get("/layout/styles.css")

        self.assertIsNotNone(cache.get(LAYOUT_STYLESHEET_CACHE_KEY))

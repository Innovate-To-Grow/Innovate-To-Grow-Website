from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.cms.models import SiteSettings
from apps.cms.services.styles.theme import LAYER_ORDER_STATEMENT
from apps.cms.views.theme import THEME_CACHE_KEY, etag_matches


class ThemeStylesheetViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        settings = SiteSettings.load()
        settings.custom_css = ".site-header { color: red; }"
        settings.save()

    def test_serves_the_theme_as_css(self):
        response = self.client.get("/layout/theme.css")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/css; charset=utf-8")
        body = response.content.decode()
        self.assertTrue(body.startswith(LAYER_ORDER_STATEMENT))
        self.assertIn("@layer itg.tokens {\n:root {", body)
        self.assertIn("@layer itg.overrides {\n.site-header { color: red; }\n}", body)

    def test_cache_headers_let_the_cdn_serve_a_stale_copy(self):
        response = self.client.get("/layout/theme.css")

        directives = {part.strip() for part in response["Cache-Control"].split(",")}
        self.assertEqual(directives, {"public", "max-age=300", "stale-while-revalidate=86400", "stale-if-error=604800"})
        self.assertRegex(response["ETag"], r'^"[0-9a-f]{32}"$')

    def test_a_matching_etag_gets_304(self):
        etag = self.client.get("/layout/theme.css")["ETag"]

        for header in (etag, f"W/{etag}", f'"other", {etag}', "*"):
            with self.subTest(header=header):
                response = self.client.get("/layout/theme.css", HTTP_IF_NONE_MATCH=header)
                self.assertEqual(response.status_code, 304)
                self.assertEqual(response["ETag"], etag)
                self.assertIn("stale-if-error=604800", response["Cache-Control"])
                self.assertEqual(response.content, b"")

    def test_a_stale_etag_gets_the_new_body(self):
        etag = self.client.get("/layout/theme.css")["ETag"]
        settings = SiteSettings.load()
        settings.custom_css = ".site-footer { color: blue; }"
        with self.captureOnCommitCallbacks(execute=True):
            settings.save()

        response = self.client.get("/layout/theme.css", HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response["ETag"], etag)
        self.assertIn(".site-footer { color: blue; }", response.content.decode())

    def test_saving_site_settings_clears_the_cached_theme(self):
        self.client.get("/layout/theme.css")
        self.assertIsNotNone(cache.get(THEME_CACHE_KEY))

        with self.captureOnCommitCallbacks(execute=True):
            SiteSettings.load().save()

        self.assertIsNone(cache.get(THEME_CACHE_KEY))

    def test_the_old_stylesheet_url_keeps_its_unlayered_tokens(self):
        body = self.client.get("/layout/styles.css").content.decode()
        self.assertTrue(body.startswith(":root {"))
        self.assertNotIn("@layer", body)
        self.assertNotIn(".site-header", body)


class EtagMatchesTests(TestCase):
    def test_weak_comparison(self):
        self.assertTrue(etag_matches('"abc"', '"abc"'))
        self.assertTrue(etag_matches('W/"abc"', '"abc"'))
        self.assertTrue(etag_matches('"x", W/"abc"', '"abc"'))
        self.assertTrue(etag_matches("*", '"abc"'))
        self.assertFalse(etag_matches('"abd"', '"abc"'))
        self.assertFalse(etag_matches("", '"abc"'))
        self.assertFalse(etag_matches("garbage", '"abc"'))

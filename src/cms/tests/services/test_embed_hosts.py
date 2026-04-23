from django.test import TestCase

from cms.models import CMSEmbedAllowedHost
from cms.services.embed_hosts import (
    InvalidEmbedURL,
    get_allowed_hosts,
    invalidate_cache,
    is_host_allowed,
    parse_embed_url,
)


class ParseEmbedURLTests(TestCase):
    def test_rejects_empty(self):
        with self.assertRaises(InvalidEmbedURL):
            parse_embed_url("")

    def test_rejects_non_string(self):
        with self.assertRaises(InvalidEmbedURL):
            parse_embed_url(None)  # type: ignore[arg-type]

    def test_rejects_http(self):
        with self.assertRaises(InvalidEmbedURL):
            parse_embed_url("http://example.com/path")

    def test_rejects_missing_host(self):
        with self.assertRaises(InvalidEmbedURL):
            parse_embed_url("https:///path")

    def test_lowercases_host(self):
        _, host = parse_embed_url("https://DOCS.GOOGLE.COM/forms/d/xyz/viewform")
        self.assertEqual(host, "docs.google.com")

    def test_strips_port(self):
        _, host = parse_embed_url("https://example.com:8443/thing")
        self.assertEqual(host, "example.com")

    def test_returns_scheme(self):
        scheme, _ = parse_embed_url("https://example.com/x")
        self.assertEqual(scheme, "https")


class IsHostAllowedTests(TestCase):
    def setUp(self):
        CMSEmbedAllowedHost.objects.all().delete()
        invalidate_cache()

    def tearDown(self):
        invalidate_cache()

    def _add(self, hostname, active=True):
        CMSEmbedAllowedHost.objects.create(hostname=hostname, is_active=active)
        invalidate_cache()

    def test_exact_match(self):
        self._add("docs.google.com")
        self.assertTrue(is_host_allowed("docs.google.com"))
        self.assertFalse(is_host_allowed("other.google.com"))

    def test_wildcard_matches_subdomain(self):
        self._add("*.youtube.com")
        self.assertTrue(is_host_allowed("www.youtube.com"))
        self.assertTrue(is_host_allowed("m.youtube.com"))
        self.assertTrue(is_host_allowed("a.b.youtube.com"))

    def test_wildcard_matches_base(self):
        self._add("*.youtube.com")
        self.assertTrue(is_host_allowed("youtube.com"))

    def test_wildcard_does_not_match_sibling(self):
        self._add("*.youtube.com")
        self.assertFalse(is_host_allowed("fakeyoutube.com"))
        self.assertFalse(is_host_allowed("youtube.com.attacker.io"))

    def test_inactive_rows_ignored(self):
        self._add("docs.google.com", active=False)
        self.assertFalse(is_host_allowed("docs.google.com"))

    def test_empty_host_is_not_allowed(self):
        self._add("docs.google.com")
        self.assertFalse(is_host_allowed(""))

    def test_case_insensitive_lookup(self):
        self._add("docs.google.com")
        self.assertTrue(is_host_allowed("DOCS.GOOGLE.COM"))

    def test_none_host_is_not_allowed(self):
        self._add("docs.google.com")
        self.assertFalse(is_host_allowed(None))  # type: ignore[arg-type]

    def test_whitespace_only_host_is_not_allowed(self):
        self._add("docs.google.com")
        # Defensive check: the validator already parses+normalizes, but
        # `is_host_allowed` is called from other sites too.
        self.assertFalse(is_host_allowed("   "))

    def test_wildcard_exact_base_match(self):
        """Extra belt-and-suspenders for the wildcard base-match path."""
        self._add("*.calendly.com")
        self.assertTrue(is_host_allowed("calendly.com"))
        self.assertTrue(is_host_allowed("team.calendly.com"))
        self.assertFalse(is_host_allowed("calendly.com.attacker.io"))


class GetAllowedHostsCachingTests(TestCase):
    def setUp(self):
        CMSEmbedAllowedHost.objects.all().delete()
        invalidate_cache()

    def tearDown(self):
        invalidate_cache()

    def test_cache_invalidated_by_helper(self):
        CMSEmbedAllowedHost.objects.create(hostname="one.example.com")
        self.assertEqual(get_allowed_hosts(), ["one.example.com"])

        CMSEmbedAllowedHost.objects.create(hostname="two.example.com")
        invalidate_cache()
        self.assertCountEqual(get_allowed_hosts(), ["one.example.com", "two.example.com"])

    def test_cache_survives_between_calls_without_invalidation(self):
        """A second `get_allowed_hosts()` call with no writes must be a cache hit.

        We prove this by priming the cache, then dropping the row directly via
        `_base_manager` (which bypasses signals) — the cached copy still wins.
        Calling `invalidate_cache()` afterwards forces a DB re-read.
        """
        CMSEmbedAllowedHost.objects.create(hostname="cached.example.com")
        self.assertEqual(get_allowed_hosts(), ["cached.example.com"])

        # Bypass signals to simulate a stale DB state vs. live cache.
        CMSEmbedAllowedHost._base_manager.filter(hostname="cached.example.com").delete()
        # Cache still reports the old row — proves we're not re-querying.
        self.assertEqual(get_allowed_hosts(), ["cached.example.com"])

        invalidate_cache()
        self.assertEqual(get_allowed_hosts(), [])

from django.core.cache import cache
from django.test import TestCase

from apps.cms.models import CMSEmbedAllowedHost
from apps.cms.services.sanitization.embed_hosts import invalidate_cache


class CMSEmbedHostsAPITests(TestCase):
    def setUp(self):
        cache.clear()
        CMSEmbedAllowedHost.objects.all().delete()
        CMSEmbedAllowedHost.objects.create(hostname="docs.example.com", is_active=True)
        CMSEmbedAllowedHost.objects.create(hostname="*.video.example.com", is_active=True)
        CMSEmbedAllowedHost.objects.create(hostname="disabled.example.com", is_active=False)
        invalidate_cache()

    def tearDown(self):
        invalidate_cache()

    def test_public_response_has_hosts_revision_etag_and_cache_policy(self):
        response = self.client.get("/cms/embed-hosts/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["hosts"], ["*.video.example.com", "docs.example.com"])
        self.assertEqual(len(response.json()["revision"]), 64)
        self.assertEqual(response["ETag"], f'"{response.json()["revision"]}"')
        self.assertIn("public", response["Cache-Control"])
        self.assertNotIn("disabled.example.com", response.json()["hosts"])

    def test_matching_etag_returns_not_modified(self):
        initial = self.client.get("/cms/embed-hosts/")

        response = self.client.get("/cms/embed-hosts/", HTTP_IF_NONE_MATCH=initial["ETag"])

        self.assertEqual(response.status_code, 304)
        self.assertEqual(response["ETag"], initial["ETag"])
        self.assertEqual(response.content, b"")

    def test_revision_changes_when_active_policy_changes(self):
        initial = self.client.get("/cms/embed-hosts/").json()["revision"]
        CMSEmbedAllowedHost.objects.create(hostname="new.example.com", is_active=True)
        # The model signal invalidates the cached host list on commit. TestCase
        # captures on_commit callbacks, so invalidate explicitly for this
        # content-addressed revision assertion.
        invalidate_cache()

        updated = self.client.get("/cms/embed-hosts/").json()["revision"]

        self.assertNotEqual(updated, initial)

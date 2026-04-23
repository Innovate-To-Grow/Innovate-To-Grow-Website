"""Tests for the CMSEmbedAllowedHost model and admin."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from authn.models import ContactEmail
from cms.models import CMSEmbedAllowedHost
from cms.services.embed_hosts import get_allowed_hosts, invalidate_cache

Member = get_user_model()


class CMSEmbedAllowedHostModelTests(TestCase):
    def setUp(self):
        CMSEmbedAllowedHost.objects.all().delete()
        invalidate_cache()

    def tearDown(self):
        invalidate_cache()

    def test_clean_accepts_exact_host(self):
        host = CMSEmbedAllowedHost(hostname="api.example.com")
        host.full_clean()
        self.assertEqual(host.hostname, "api.example.com")

    def test_clean_accepts_wildcard(self):
        host = CMSEmbedAllowedHost(hostname="*.example.com")
        host.full_clean()
        self.assertEqual(host.hostname, "*.example.com")

    def test_clean_lowercases(self):
        host = CMSEmbedAllowedHost(hostname="API.EXAMPLE.COM")
        host.full_clean()
        self.assertEqual(host.hostname, "api.example.com")

    def test_clean_rejects_invalid(self):
        for bad in ("", "no-tld", "has space.com", "http://docs.google.com", "*.*.com"):
            with self.assertRaises(ValidationError, msg=f"{bad!r} should fail"):
                CMSEmbedAllowedHost(hostname=bad).full_clean()

    def test_str(self):
        host = CMSEmbedAllowedHost(hostname="example.com")
        self.assertEqual(str(host), "example.com")


class CMSEmbedAllowedHostAdminTests(TestCase):
    def setUp(self):
        CMSEmbedAllowedHost.objects.all().delete()
        invalidate_cache()
        self.admin = Member.objects.create_superuser(
            password="testpass123",
            first_name="Embed",
            last_name="Host",
        )
        ContactEmail.objects.create(
            member=self.admin,
            email_address="embed-host-admin@example.com",
            email_type="primary",
            verified=True,
        )
        self.client.login(username="embed-host-admin@example.com", password="testpass123")

    def tearDown(self):
        invalidate_cache()

    def test_changelist_loads(self):
        resp = self.client.get(reverse("admin:cms_cmsembedallowedhost_changelist"))
        self.assertEqual(resp.status_code, 200)

    def test_create_via_admin(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        resp = self.client.post(
            url,
            data={
                "hostname": "demo.example.com",
                "description": "Demo",
                "is_active": "on",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(CMSEmbedAllowedHost.objects.filter(hostname="demo.example.com").exists())

    def test_save_invalidates_cache(self):
        CMSEmbedAllowedHost.objects.create(hostname="one.example.com")
        self.assertEqual(get_allowed_hosts(), ["one.example.com"])

        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(
            url,
            data={
                "hostname": "two.example.com",
                "description": "",
                "is_active": "on",
            },
            follow=True,
        )
        self.assertIn("two.example.com", get_allowed_hosts())

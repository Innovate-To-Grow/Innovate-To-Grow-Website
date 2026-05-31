"""Tests for FrozenPageAdmin: import-from-URL view, re-freeze action, auto-capture."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.cms.admin.cms.frozen_page import FrozenPageAdmin
from apps.cms.models import FrozenPage
from apps.cms.services.freeze import BlockedURLError, FrozenResult

User = get_user_model()

_FREEZE_TARGET = "apps.cms.services.freeze.freeze_url"


def _result(html="<!DOCTYPE html><html><body>frozen</body></html>", title="Imported", byte_size=42):
    return FrozenResult(final_url="https://example.com/", title=title, html=html, byte_size=byte_size)


def _request(user):
    request = RequestFactory().post("/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class FrozenPageAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email="frozen-admin@example.com", password="pw", first_name="Frozen", last_name="Admin"
        )
        self.client.force_login(self.admin_user)
        self.model_admin = FrozenPageAdmin(FrozenPage, AdminSite())

    def test_import_view_renders(self):
        resp = self.client.get(reverse("admin:cms_frozenpage_import_url"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Import")

    @patch(_FREEZE_TARGET)
    def test_import_post_creates_and_redirects(self, mock_freeze):
        mock_freeze.return_value = _result()
        resp = self.client.post(
            reverse("admin:cms_frozenpage_import_url"),
            {
                "source_url": "https://example.com/",
                "title": "",
                "slug": "",
                "status": "published",
                "extra_remove_selectors": "",
                "remove_header": "on",
            },
        )
        self.assertEqual(FrozenPage.objects.count(), 1)
        page = FrozenPage.objects.get()
        self.assertEqual(page.title, "Imported")
        self.assertEqual(page.byte_size, 42)
        self.assertTrue(page.remove_header)
        self.assertTrue(page.frozen_html)
        self.assertRedirects(resp, reverse("admin:cms_frozenpage_change", args=[page.pk]))
        # The presets the form selected were passed to the freeze service.
        _, kwargs = mock_freeze.call_args
        self.assertIn("header", kwargs["remove_presets"])

    @patch(_FREEZE_TARGET)
    def test_import_post_blocked_creates_nothing(self, mock_freeze):
        mock_freeze.side_effect = BlockedURLError("blocked")
        resp = self.client.post(
            reverse("admin:cms_frozenpage_import_url"),
            {"source_url": "https://example.com/", "status": "draft", "extra_remove_selectors": ""},
        )
        self.assertEqual(FrozenPage.objects.count(), 0)
        self.assertRedirects(resp, reverse("admin:cms_frozenpage_import_url"))

    def test_import_post_invalid_form_rerenders(self):
        resp = self.client.post(
            reverse("admin:cms_frozenpage_import_url"),
            {"source_url": "not a url", "status": "draft"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FrozenPage.objects.count(), 0)

    @patch(_FREEZE_TARGET)
    def test_refreeze_action_recaptures(self, mock_freeze):
        mock_freeze.return_value = _result(html="<html>NEW</html>", title="T", byte_size=15)
        page = FrozenPage.objects.create(
            source_url="https://example.com/", slug="p", status="published", frozen_html="<old>"
        )
        self.model_admin.refreeze_selected(_request(self.admin_user), FrozenPage.objects.filter(pk=page.pk))
        page.refresh_from_db()
        self.assertEqual(page.frozen_html, "<html>NEW</html>")
        self.assertEqual(page.byte_size, 15)

    @patch(_FREEZE_TARGET)
    def test_refreeze_action_handles_block_error(self, mock_freeze):
        mock_freeze.side_effect = BlockedURLError("nope")
        page = FrozenPage.objects.create(
            source_url="https://example.com/", slug="p", status="published", frozen_html="<old>"
        )
        self.model_admin.refreeze_selected(_request(self.admin_user), FrozenPage.objects.filter(pk=page.pk))
        page.refresh_from_db()
        self.assertEqual(page.frozen_html, "<old>")  # unchanged on failure

    @patch(_FREEZE_TARGET)
    def test_save_model_auto_freezes_on_first_capture(self, mock_freeze):
        mock_freeze.return_value = _result(html="<html>A</html>", title="Auto", byte_size=9)
        obj = FrozenPage(source_url="https://example.com/", slug="auto", status="draft")
        self.model_admin.save_model(_request(self.admin_user), obj, form=None, change=False)
        obj.refresh_from_db()
        self.assertEqual(obj.frozen_html, "<html>A</html>")
        self.assertEqual(obj.byte_size, 9)

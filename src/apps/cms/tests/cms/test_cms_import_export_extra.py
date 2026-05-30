"""Extra coverage for CMS page import/export helpers and the CMSPage admin view methods."""

import json
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.cms.admin.cms.cms_page import CMSPageAdmin
from apps.cms.admin.cms.page_admin.import_export import (
    process_page_data,
    validate_page_data,
)
from apps.cms.models import BLOCK_TYPE_CHOICES, CMSBlock, CMSPage

Member = get_user_model()


class ProcessPageDataTests(TestCase):
    def setUp(self):
        self.block_keys = {choice[0] for choice in BLOCK_TYPE_CHOICES}

    def test_validate_required_flags_missing_fields(self):
        result, blocks, existing = validate_page_data({}, self.block_keys, validate_required=True)
        self.assertIn("Missing 'slug'.", result["errors"])
        self.assertIn("Missing 'route'.", result["errors"])
        self.assertIn("Missing 'title'.", result["errors"])
        self.assertIsNone(existing)
        self.assertEqual(blocks, [])

    def test_validate_unknown_block_type_reported(self):
        page_data = {
            "slug": "p",
            "route": "/p",
            "title": "P",
            "blocks": [{"block_type": "totally_unknown", "data": {}}],
        }
        result, _, _ = validate_page_data(page_data, self.block_keys, validate_required=True)
        self.assertTrue(any("unknown type 'totally_unknown'" in e for e in result["errors"]))

    def test_validate_block_data_error_reported(self):
        # rich_text block with malformed data triggers validate_block_data to raise.
        with patch(
            "apps.cms.admin.cms.page_admin.import_export.validate_block_data",
            side_effect=ValueError("bad block payload"),
        ):
            page_data = {
                "slug": "p",
                "route": "/p",
                "title": "P",
                "blocks": [{"block_type": "rich_text", "data": {"body_html": "<p>x</p>"}}],
            }
            result, _, _ = validate_page_data(page_data, self.block_keys, validate_required=True)
        self.assertTrue(any("bad block payload" in e for e in result["errors"]))

    def test_existing_page_marks_update_action(self):
        CMSPage.objects.create(slug="dupe", route="/dupe", title="Dupe", status="draft")
        page_data = {"slug": "dupe", "route": "/dupe", "title": "Dupe"}
        result, _, existing = validate_page_data(page_data, self.block_keys, validate_required=True)
        self.assertEqual(result["action"], "update")
        self.assertIsNotNone(existing)

    def test_process_records_exception_during_upsert(self):
        # Force replace_page_blocks to raise so the execute branch records the error.
        with patch(
            "apps.cms.admin.cms.page_admin.import_export.replace_page_blocks",
            side_effect=RuntimeError("write failure"),
        ):
            results = process_page_data(
                [{"slug": "x", "route": "/x", "title": "X", "blocks": []}],
                action="execute",
                default_status="draft",
                validate_required=True,
            )
        self.assertEqual(len(results), 1)
        self.assertIn("write failure", results[0]["errors"])
        self.assertNotIn("success", results[0])


class CMSPageImportViewTests(TestCase):
    def setUp(self):
        self.staff = Member.objects.create_superuser(password="testpass123", first_name="Imp", last_name="Admin")
        ContactEmail.objects.create(
            member=self.staff, email_address="imp-admin@example.com", email_type="primary", verified=True
        )
        self.client.login(username="imp-admin@example.com", password="testpass123")
        self.url = reverse("admin:cms_cmspage_import")

    def test_get_renders_upload_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import CMS Pages")

    def test_post_without_file_shows_error(self):
        response = self.client.post(self.url, {"action": "dry_run"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please select a JSON file to import.")

    def test_post_invalid_json_shows_error(self):
        upload = SimpleUploadedFile("bad.json", b"{ not json", content_type="application/json")
        response = self.client.post(self.url, {"json_file": upload, "action": "dry_run"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid JSON file:")

    def test_post_bad_format_shows_error(self):
        upload = SimpleUploadedFile(
            "bad-format.json",
            json.dumps({"version": 1, "not_pages": []}).encode("utf-8"),
            content_type="application/json",
        )
        response = self.client.post(self.url, {"json_file": upload, "action": "dry_run"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "expected a JSON object with a")

    def test_execute_with_errors_emits_warning(self):
        # A page missing required slug/route/title cannot import; execute should warn.
        upload = SimpleUploadedFile(
            "errors.json",
            json.dumps({"version": 1, "pages": [{"blocks": []}]}).encode("utf-8"),
            content_type="application/json",
        )
        response = self.client.post(self.url, {"json_file": upload, "action": "execute"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "had errors")
        self.assertEqual(CMSPage.objects.count(), 0)


class CMSPageAdminMethodTests(TestCase):
    def setUp(self):
        self.admin = CMSPageAdmin(CMSPage, AdminSite())

    def test_block_count_uses_annotation_when_present(self):
        page = CMSPage.objects.create(slug="annotated", route="/annotated", title="A", status="draft")
        page._block_count = 7  # simulate the annotated queryset value
        self.assertEqual(self.admin.block_count(page), 7)

    def test_block_count_falls_back_to_query(self):
        page = CMSPage.objects.create(slug="counted", route="/counted", title="C", status="draft")
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=0, data={})
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=1, data={})
        # No _block_count attribute -> falls back to obj.blocks.count().
        self.assertEqual(self.admin.block_count(page), 2)

    def test_published_page_makes_slug_readonly(self):
        page = CMSPage.objects.create(slug="pub", route="/pub", title="Pub", status="published")
        request = type("Req", (), {})()
        readonly = self.admin.get_readonly_fields(request, page)
        self.assertIn("slug", readonly)

    def test_draft_page_keeps_slug_editable(self):
        page = CMSPage.objects.create(slug="drafty", route="/drafty", title="Draft", status="draft")
        request = type("Req", (), {})()
        readonly = self.admin.get_readonly_fields(request, page)
        self.assertNotIn("slug", readonly)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class CMSPageAdminViewMethodTests(TestCase):
    def setUp(self):
        self.staff = Member.objects.create_superuser(password="testpass123", first_name="View", last_name="Admin")
        ContactEmail.objects.create(
            member=self.staff, email_address="view-admin@example.com", email_type="primary", verified=True
        )
        self.client.login(username="view-admin@example.com", password="testpass123")

    def test_add_view_injects_editor_context(self):
        response = self.client.get(reverse("admin:cms_cmspage_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CMS_ROUTE_EDITOR")

    def test_save_related_persists_blocks_from_json(self):
        # Posting the add form with blocks_json drives save_related -> save_blocks_from_json.
        blocks_json = json.dumps(
            [{"block_type": "rich_text", "admin_label": "Body", "data": {"body_html": "<p>Hi</p>"}}]
        )
        response = self.client.post(
            reverse("admin:cms_cmspage_add"),
            {
                "slug": "save-related-page",
                "route": "/save-related-page",
                "title": "Save Related",
                "meta_description": "",
                "page_css_class": "",
                "page_css": "",
                "status": "draft",
                "sort_order": 0,
                "published_at": "",
                "blocks_json": blocks_json,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        page = CMSPage.objects.get(slug="save-related-page")
        self.assertEqual(page.blocks.count(), 1)
        self.assertEqual(page.blocks.first().block_type, "rich_text")

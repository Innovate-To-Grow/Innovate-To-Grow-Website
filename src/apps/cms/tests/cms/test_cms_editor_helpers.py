"""Coverage for CMS page editor helpers: block persistence, asset responses, route conflict."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from apps.cms.admin.cms.page_admin.editor.assets import (
    assets_list_response,
    assets_upload_response,
    serialize_asset,
)
from apps.cms.admin.cms.page_admin.editor.blocks import save_blocks_from_json
from apps.cms.admin.cms.page_admin.editor.responses import route_conflict_response
from apps.cms.models import CMSAsset, CMSBlock, CMSPage

Member = get_user_model()


class _MessageCollector:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, request, message):
        self.errors.append(message)

    def warning(self, request, message):
        self.warnings.append(message)


class _FakeRequest:
    def __init__(self, blocks_json):
        self.POST = {"blocks_json": blocks_json} if blocks_json is not None else {}


class SaveBlocksFromJsonTests(TestCase):
    def setUp(self):
        self.page = CMSPage.objects.create(slug="blocks-host", route="/blocks-host", title="Host", status="draft")

    def test_empty_blocks_json_is_noop(self):
        messages = _MessageCollector()
        save_blocks_from_json(_FakeRequest(""), self.page, messages)
        self.assertEqual(messages.errors, [])
        self.assertEqual(messages.warnings, [])

    def test_non_list_payload_reports_error(self):
        messages = _MessageCollector()
        save_blocks_from_json(_FakeRequest(json.dumps({"not": "a list"})), self.page, messages)
        self.assertEqual(messages.errors, ["Invalid blocks data: expected a JSON array."])

    def test_invalid_json_reports_error(self):
        messages = _MessageCollector()
        save_blocks_from_json(_FakeRequest("{not json"), self.page, messages)
        self.assertEqual(messages.errors, ["Invalid blocks JSON: could not parse input."])

    def test_non_dict_block_is_skipped_with_warning(self):
        messages = _MessageCollector()
        save_blocks_from_json(_FakeRequest(json.dumps(["not-a-dict"])), self.page, messages)
        self.assertTrue(any("invalid format, skipped" in w for w in messages.warnings))
        self.assertEqual(self.page.blocks.count(), 0)

    def test_validation_error_block_skipped_with_warning(self):
        from django.core.exceptions import ValidationError

        messages = _MessageCollector()
        with patch(
            "apps.cms.admin.cms.page_admin.editor.blocks.validate_block_data",
            side_effect=ValidationError(["bad data here"]),
        ):
            save_blocks_from_json(
                _FakeRequest(json.dumps([{"block_type": "rich_text", "data": {}}])),
                self.page,
                messages,
            )
        self.assertTrue(any("bad data here" in w for w in messages.warnings))
        self.assertEqual(self.page.blocks.count(), 0)

    def test_type_error_block_skipped_with_warning(self):
        messages = _MessageCollector()
        with patch(
            "apps.cms.admin.cms.page_admin.editor.blocks.validate_block_data",
            side_effect=KeyError("missing"),
        ):
            save_blocks_from_json(
                _FakeRequest(json.dumps([{"block_type": "rich_text", "data": {}}])),
                self.page,
                messages,
            )
        self.assertTrue(any("Invalid block data format" in w for w in messages.warnings))
        self.assertEqual(self.page.blocks.count(), 0)

    def test_valid_blocks_persisted(self):
        messages = _MessageCollector()
        CMSBlock.objects.create(page=self.page, block_type="rich_text", sort_order=0, data={})
        save_blocks_from_json(
            _FakeRequest(
                json.dumps([{"block_type": "rich_text", "admin_label": "Body", "data": {"body_html": "<p>x</p>"}}])
            ),
            self.page,
            messages,
        )
        self.assertEqual(messages.errors, [])
        self.assertEqual(self.page.blocks.count(), 1)


class AssetsResponseTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_serialize_asset_handles_missing_file_size(self):
        asset = CMSAsset.objects.create(
            name="Pic",
            file=SimpleUploadedFile("pic.png", b"\x89PNG\r\n\x1a\n", content_type="image/png"),
        )
        # Force asset.file.size to raise so the OSError/ValueError branch sets size=None.
        with patch.object(type(asset.file), "size", property(lambda self: (_ for _ in ()).throw(OSError("gone")))):
            payload = serialize_asset(asset)
        self.assertIsNone(payload["size"])
        self.assertEqual(payload["extension"], "png")
        self.assertTrue(payload["is_image"])

    def test_list_rejects_non_get(self):
        response = assets_list_response(self.factory.post("/assets/"))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(json.loads(response.content)["detail"], "Method not allowed.")

    def test_list_invalid_limit_defaults_to_50(self):
        for i in range(3):
            CMSAsset.objects.create(
                name=f"Doc {i}",
                file=SimpleUploadedFile(f"doc{i}.pdf", b"%PDF-1.7\n", content_type="application/pdf"),
            )
        response = assets_list_response(self.factory.get("/assets/", {"limit": "not-a-number"}))
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        # Limit falls back to 50, so all 3 assets are returned.
        self.assertEqual(body["total"], 3)
        self.assertEqual(len(body["assets"]), 3)

    def test_upload_rejects_non_post(self):
        response = assets_upload_response(self.factory.get("/assets/upload/"))
        self.assertEqual(response.status_code, 405)

    def test_upload_without_file_returns_400(self):
        response = assets_upload_response(self.factory.post("/assets/upload/", {}))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["detail"], "Select a file to upload.")

    def test_upload_unexpected_validation_error_returns_500(self):
        request = self.factory.post(
            "/assets/upload/",
            {"file": SimpleUploadedFile("x.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")},
        )
        with patch.object(CMSAsset, "full_clean", side_effect=RuntimeError("boom")):
            response = assets_upload_response(request)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(json.loads(response.content)["detail"], "An unexpected error occurred.")

    def test_upload_unexpected_save_error_returns_500(self):
        request = self.factory.post(
            "/assets/upload/",
            {"file": SimpleUploadedFile("ok.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")},
        )
        with patch.object(CMSAsset, "save", side_effect=RuntimeError("disk full")):
            response = assets_upload_response(request)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(json.loads(response.content)["detail"], "An unexpected error occurred.")

    def test_upload_validation_error_without_message_dict(self):
        from django.core.exceptions import ValidationError

        request = self.factory.post(
            "/assets/upload/",
            {"file": SimpleUploadedFile("ok.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")},
        )
        # A non-field ValidationError has no message_dict, exercising the else branch.
        with patch.object(CMSAsset, "full_clean", side_effect=ValidationError(["plain validation message"])):
            response = assets_upload_response(request)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertEqual(body["detail"], "plain validation message")


class RouteConflictResponseTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_invalid_route_returns_validation_message(self):
        # An empty/invalid route fails validate_cms_route and reports is_valid False.
        with patch(
            "apps.cms.admin.cms.page_admin.editor.responses.validate_cms_route",
            side_effect=__import__("django.core.exceptions", fromlist=["ValidationError"]).ValidationError(
                ["Route cannot be blank."]
            ),
        ):
            response = route_conflict_response(self.factory.get("/route-conflict/", {"route": "bad"}))
        body = json.loads(response.content)
        self.assertFalse(body["is_valid"])
        self.assertEqual(body["message"], "Route cannot be blank.")
        self.assertFalse(body["has_conflict"])

    def test_excludes_current_page_from_conflict_check(self):
        page = CMSPage.objects.create(slug="self", route="/self-route", title="Self", status="published")
        response = route_conflict_response(
            self.factory.get("/route-conflict/", {"route": "/self-route", "page_id": str(page.pk)})
        )
        body = json.loads(response.content)
        # The page is excluded from the conflict query, so no conflict reported.
        self.assertTrue(body["is_valid"])
        self.assertFalse(body["has_conflict"])

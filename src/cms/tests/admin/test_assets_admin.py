import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from authn.models import ContactEmail
from cms.models import CMSAsset
from cms.models.media import MAX_ASSET_UPLOAD_BYTES

Member = get_user_model()


class CMSAssetAdminTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.temp_media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media_root)
        self.media_override.enable()

        self.admin_user = Member.objects.create_superuser(
            password="testpass123",
            first_name="Assets",
            last_name="Admin",
        )
        ContactEmail.objects.create(
            member=self.admin_user,
            email_address="assets-admin@example.com",
            email_type="primary",
            verified=True,
        )
        self.client.login(username="assets-admin@example.com", password="testpass123")

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.temp_media_root, ignore_errors=True)

    def test_asset_admin_change_view_shows_public_url_and_preview(self):
        asset = CMSAsset.objects.create(
            name="Acme Logo",
            file=SimpleUploadedFile(
                "acme-logo.svg",
                b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                content_type="image/svg+xml",
            ),
        )

        response = self.client.get(reverse("admin:cms_cmsasset_change", args=[asset.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(asset.public_url, response.content.decode())
        self.assertIn("Upload reusable CMS media here", response.content.decode())

    def test_asset_picker_list_endpoint_returns_assets(self):
        asset = CMSAsset.objects.create(
            name="Campus Map",
            file=SimpleUploadedFile("map.pdf", b"%PDF-1.7\n", content_type="application/pdf"),
        )

        response = self.client.get(reverse("admin:cms_cmspage_assets"), {"q": "campus"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["assets"][0]["id"], str(asset.pk))
        self.assertEqual(payload["assets"][0]["name"], "Campus Map")
        self.assertEqual(payload["assets"][0]["extension"], "pdf")
        self.assertFalse(payload["assets"][0]["is_image"])
        self.assertEqual(payload["assets"][0]["public_url"], asset.public_url)

    def test_asset_picker_list_search_does_not_match_storage_path(self):
        asset = CMSAsset.objects.create(
            name="Visible Name",
            file=SimpleUploadedFile("map.pdf", b"%PDF-1.7\n", content_type="application/pdf"),
        )

        response = self.client.get(reverse("admin:cms_cmspage_assets"), {"q": str(asset.pk)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 0)
        self.assertEqual(payload["assets"], [])

    def test_asset_picker_image_filter_applies_before_limit(self):
        image = CMSAsset.objects.create(
            name="Older Image",
            file=SimpleUploadedFile(
                "older-image.png",
                b"\x89PNG\r\n\x1a\n",
                content_type="image/png",
            ),
        )
        CMSAsset.objects.filter(pk=image.pk).update(updated_at=timezone.now() - timedelta(days=1))
        for index in range(60):
            CMSAsset.objects.create(
                name=f"Recent Document {index:02d}",
                file=SimpleUploadedFile(
                    f"recent-document-{index:02d}.pdf",
                    b"%PDF-1.7\n",
                    content_type="application/pdf",
                ),
            )

        response = self.client.get(reverse("admin:cms_cmspage_assets"), {"type": "image", "limit": "50"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["assets"][0]["id"], str(image.pk))
        self.assertTrue(payload["assets"][0]["is_image"])

    def test_asset_picker_upload_endpoint_creates_image_asset(self):
        response = self.client.post(
            reverse("admin:cms_cmspage_asset_upload"),
            {
                "name": "Uploaded Logo",
                "file": SimpleUploadedFile(
                    "uploaded-logo.png",
                    b"\x89PNG\r\n\x1a\n",
                    content_type="image/png",
                ),
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["asset"]
        self.assertEqual(payload["name"], "Uploaded Logo")
        self.assertEqual(payload["extension"], "png")
        self.assertTrue(payload["is_image"])
        self.assertTrue(CMSAsset.objects.filter(pk=payload["id"]).exists())

    def test_asset_picker_image_upload_rejects_document_asset(self):
        response = self.client.post(
            reverse("admin:cms_cmspage_asset_upload") + "?type=image",
            {
                "name": "Uploaded PDF",
                "file": SimpleUploadedFile("uploaded.pdf", b"%PDF-1.7\n", content_type="application/pdf"),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Select an image asset for this field.")
        self.assertFalse(CMSAsset.objects.filter(name="Uploaded PDF").exists())

    def test_asset_picker_upload_rejects_invalid_extension(self):
        response = self.client.post(
            reverse("admin:cms_cmspage_asset_upload"),
            {
                "name": "HTML",
                "file": SimpleUploadedFile("page.html", b"<html></html>", content_type="text/html"),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_asset_picker_upload_rejects_oversize_file(self):
        response = self.client.post(
            reverse("admin:cms_cmspage_asset_upload"),
            {
                "name": "Too Large",
                "file": SimpleUploadedFile(
                    "too-large.txt",
                    b"x" * (MAX_ASSET_UPLOAD_BYTES + 1),
                    content_type="text/plain",
                ),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "The uploaded asset failed validation.")

    def test_asset_picker_upload_requires_staff(self):
        self.client.logout()

        response = self.client.post(reverse("admin:cms_cmspage_asset_upload"))

        self.assertIn(response.status_code, (302, 403))

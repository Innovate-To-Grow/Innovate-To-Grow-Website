import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from authn.models import ContactEmail
from cms.models import CMSAsset

Member = get_user_model()


class CMSAssetAdminTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.temp_media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media_root)
        self.media_override.enable()

        self.admin_user = Member.objects.create_superuser(password="testpass123")
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
        self.assertIn("Upload sponsor logos here", response.content.decode())

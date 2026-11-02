"""The CKEditor 5 image-upload endpoint mounted at ``/ckeditor5/image_upload/``.

django-ckeditor-5 verifies every upload with ``PIL.Image.open(...).verify()`` and maps Pillow's
``OSError`` to a 400. These pin that contract, plus our ``CKEDITOR_5_FILE_UPLOAD_PERMISSION =
"staff"`` gate, so a Pillow or django-ckeditor-5 upgrade that changes either fails CI.
"""

import io
import shutil
import tempfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.authn.models import Member

UPLOAD_URL = "/ckeditor5/image_upload/"


def _png_upload(name="diagram.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), (0, 90, 160)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class CKEditorImageUploadTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.client = APIClient()

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _login(self, *, is_staff):
        member = Member.objects.create_user(password="pw-12345678", first_name="Editor", is_staff=is_staff)
        self.client.force_login(member)

    def test_staff_upload_of_valid_png_is_stored(self):
        self._login(is_staff=True)

        response = self.client.post(UPLOAD_URL, {"upload": _png_upload()}, format="multipart")

        self.assertEqual(response.status_code, 200)
        url = response.json()["url"]
        self.assertTrue(url.startswith("/media/"))
        self.assertTrue(url.endswith(".png"))

    def test_non_image_upload_is_rejected_by_pillow_verify(self):
        self._login(is_staff=True)
        upload = SimpleUploadedFile("notes.png", b"not really an image", content_type="image/png")

        response = self.client.post(UPLOAD_URL, {"upload": upload}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_non_staff_member_cannot_upload(self):
        self._login(is_staff=False)

        response = self.client.post(UPLOAD_URL, {"upload": _png_upload()}, format="multipart")

        self.assertEqual(response.status_code, 403)

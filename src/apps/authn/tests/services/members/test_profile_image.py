"""Tests for apps.authn.services.members.profile_image."""

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from apps.authn.admin.members.forms import Base64ImageField
from apps.authn.services.members.profile_image import (
    DIMENSIONS_ERROR,
    ProfileImageError,
    encode_profile_image,
)
from apps.authn.tests.helpers import PNG_BOMB


def _bomb_upload():
    return SimpleUploadedFile("bomb.png", PNG_BOMB, content_type="image/png")


class DecompressionBombTests(SimpleTestCase):
    """A tiny PNG declaring 50000x5000 px passes the size cap and magic-byte check; Pillow raises
    ``DecompressionBombError`` (a plain ``Exception``) when opening it, which must surface as a
    400/form error on both upload paths rather than a 500."""

    def test_encode_profile_image_rejects_bomb(self):
        with self.assertRaisesMessage(ProfileImageError, DIMENSIONS_ERROR):
            encode_profile_image(_bomb_upload())

    def test_base64_image_field_converts_bomb_to_validation_error(self):
        with self.assertRaisesMessage(ValidationError, DIMENSIONS_ERROR):
            Base64ImageField().to_python(_bomb_upload())

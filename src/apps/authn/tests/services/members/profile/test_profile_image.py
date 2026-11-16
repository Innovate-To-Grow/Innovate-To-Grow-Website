"""Tests for apps.authn.services.members.profile_image."""

import base64
import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from apps.authn.admin.members.forms import Base64ImageField
from apps.authn.services.members.profile_image import (
    DIMENSIONS_ERROR,
    MAX_DIMENSION,
    ProfileImageError,
    build_profile_image_data_uri,
    encode_profile_image,
)
from apps.authn.tests.helpers import PNG_BOMB


def _bomb_upload():
    return SimpleUploadedFile("bomb.png", PNG_BOMB, content_type="image/png")


def _encode(image, pillow_format, **save_kwargs):
    buffer = io.BytesIO()
    image.save(buffer, format=pillow_format, **save_kwargs)
    return buffer.getvalue()


def _decode_data_uri(data_uri):
    header, _, payload = data_uri.partition(",")
    return header, base64.b64decode(payload)


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


class DownscaleTests(SimpleTestCase):
    """Oversized uploads are re-encoded by Pillow (``thumbnail`` + ``save``) before storage. These pin
    the observable contract — output format, dimensions, mode and alpha — so a Pillow upgrade that
    changes how ``thumbnail``/``save`` behave for our inputs fails here rather than in production."""

    def _downscaled(self, raw, mime):
        header, resized = _decode_data_uri(build_profile_image_data_uri(raw, mime))
        self.assertEqual(header, f"data:{mime};base64")
        return resized

    def test_wide_png_is_shrunk_to_max_dimension_keeping_aspect_ratio(self):
        raw = _encode(Image.new("RGB", (1200, 600), (10, 120, 200)), "PNG")

        resized = self._downscaled(raw, "image/png")

        with Image.open(io.BytesIO(resized)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (MAX_DIMENSION, MAX_DIMENSION // 2))
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.getpixel((0, 0)), (10, 120, 200))

    def test_tall_image_is_shrunk_on_its_height(self):
        # Pillow 13 resamples vertically first when the height shrinks far more than the width.
        raw = _encode(Image.new("RGB", (300, 2000), (200, 30, 30)), "PNG")

        resized = self._downscaled(raw, "image/png")

        with Image.open(io.BytesIO(resized)) as image:
            self.assertEqual(image.height, MAX_DIMENSION)
            self.assertAlmostEqual(image.width, 300 * MAX_DIMENSION / 2000, delta=1)

    def test_rgba_png_keeps_its_alpha_channel(self):
        image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
        image.paste((255, 0, 0, 255), (256, 256, 768, 768))
        raw = _encode(image, "PNG")

        resized = self._downscaled(raw, "image/png")

        with Image.open(io.BytesIO(resized)) as out:
            self.assertEqual(out.mode, "RGBA")
            self.assertEqual(out.size, (MAX_DIMENSION, MAX_DIMENSION))
            self.assertEqual(out.getpixel((0, 0))[3], 0)
            self.assertEqual(out.getpixel((256, 256)), (255, 0, 0, 255))

    def test_cmyk_jpeg_is_converted_to_rgb(self):
        raw = _encode(Image.new("CMYK", (1000, 800), (0, 0, 0, 0)), "JPEG")

        resized = self._downscaled(raw, "image/jpeg")

        with Image.open(io.BytesIO(resized)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (MAX_DIMENSION, 410))

    def test_grayscale_jpeg_stays_grayscale(self):
        raw = _encode(Image.new("L", (800, 800), 128), "JPEG")

        resized = self._downscaled(raw, "image/jpeg")

        with Image.open(io.BytesIO(resized)) as image:
            self.assertEqual(image.mode, "L")
            self.assertEqual(image.size, (MAX_DIMENSION, MAX_DIMENSION))

    def test_rgba_webp_is_resized_and_keeps_transparency(self):
        image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
        image.paste((0, 255, 0, 255), (256, 256, 768, 768))
        raw = _encode(image, "WEBP", lossless=True)

        resized = self._downscaled(raw, "image/webp")

        with Image.open(io.BytesIO(resized)) as out:
            self.assertEqual(out.format, "WEBP")
            self.assertEqual(out.size, (MAX_DIMENSION, MAX_DIMENSION))
            self.assertEqual(out.convert("RGBA").getpixel((0, 0))[3], 0)

    def test_single_frame_gif_is_resized_as_gif(self):
        raw = _encode(Image.new("P", (900, 900), 3), "GIF")

        resized = self._downscaled(raw, "image/gif")

        with Image.open(io.BytesIO(resized)) as image:
            self.assertEqual(image.format, "GIF")
            self.assertEqual(image.size, (MAX_DIMENSION, MAX_DIMENSION))

    def test_animated_gif_is_stored_unchanged(self):
        frames = [Image.new("P", (900, 900), index) for index in (1, 2)]
        buffer = io.BytesIO()
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=100)
        raw = buffer.getvalue()

        self.assertEqual(self._downscaled(raw, "image/gif"), raw)

    def test_animated_png_is_stored_unchanged(self):
        frames = [Image.new("RGB", (900, 900), color) for color in ((255, 0, 0), (0, 0, 255))]
        buffer = io.BytesIO()
        frames[0].save(buffer, format="PNG", save_all=True, append_images=frames[1:], duration=100)
        raw = buffer.getvalue()

        self.assertEqual(self._downscaled(raw, "image/png"), raw)

    def test_image_within_limit_is_stored_unchanged(self):
        raw = _encode(Image.new("RGB", (MAX_DIMENSION, 100), (1, 2, 3)), "PNG")

        self.assertEqual(self._downscaled(raw, "image/png"), raw)

    def test_mime_without_a_pillow_format_is_stored_unchanged(self):
        raw = _encode(Image.new("RGB", (1200, 1200)), "BMP")

        self.assertEqual(self._downscaled(raw, "image/bmp"), raw)

    def test_undecodable_image_falls_back_to_original_bytes(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

        with self.assertLogs("apps.authn.services.members.profile_image", level="WARNING"):
            self.assertEqual(self._downscaled(raw, "image/png"), raw)

    def test_encode_profile_image_downscales_a_real_upload(self):
        raw = _encode(Image.new("RGB", (2048, 1024), (5, 5, 5)), "JPEG")
        upload = SimpleUploadedFile("avatar.jpg", raw, content_type="image/jpeg")

        header, resized = _decode_data_uri(encode_profile_image(upload))

        self.assertEqual(header, "data:image/jpeg;base64")
        with Image.open(io.BytesIO(resized)) as image:
            self.assertEqual(image.size, (MAX_DIMENSION, MAX_DIMENSION // 2))

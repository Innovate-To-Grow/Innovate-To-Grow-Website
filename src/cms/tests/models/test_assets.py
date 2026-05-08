import io
import zipfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from cms.models import CMSAsset
from cms.models.media import MAX_ASSET_UPLOAD_BYTES


def uploaded_file(name, content, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def ooxml_file(root):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr(f"{root}/document.xml", "<xml></xml>")
    return buffer.getvalue()


class CMSAssetValidationTests(TestCase):
    def assert_asset_valid(self, name, content, content_type="application/octet-stream"):
        asset = CMSAsset(name=name, file=uploaded_file(name, content, content_type))
        asset.full_clean()

    def assert_asset_invalid(self, name, content):
        asset = CMSAsset(name=name, file=uploaded_file(name, content))
        with self.assertRaises(ValidationError):
            asset.full_clean()

    def test_allows_image_pdf_office_and_text_assets(self):
        valid_files = [
            ("logo.png", b"\x89PNG\r\n\x1a\n"),
            ("photo.jpg", b"\xff\xd8\xff\xe0image"),
            ("image.gif", b"GIF89aimage"),
            ("image.webp", b"RIFF\x00\x00\x00\x00WEBPimage"),
            ("vector.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
            ("guide.pdf", b"%PDF-1.7\n"),
            ("doc.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1doc"),
            ("sheet.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1xls"),
            ("slides.ppt", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1ppt"),
            ("doc.docx", ooxml_file("word")),
            ("sheet.xlsx", ooxml_file("xl")),
            ("slides.pptx", ooxml_file("ppt")),
            ("table.csv", b"name,value\nA,1\n"),
            ("notes.txt", b"Plain UTF-8 notes\n"),
        ]

        for name, content in valid_files:
            with self.subTest(name=name):
                self.assert_asset_valid(name, content)

    def test_rejects_web_active_or_unknown_extensions(self):
        for name in ("page.html", "script.js", "styles.css", "archive.zip"):
            with self.subTest(name=name):
                self.assert_asset_invalid(name, b"content")

    def test_rejects_unsafe_svg(self):
        self.assert_asset_invalid(
            "unsafe.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        )
        self.assert_asset_invalid(
            "handler.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'></svg>",
        )
        self.assert_asset_invalid(
            "tight-handler.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg' class='x'onload='alert(1)'></svg>",
        )

    def test_allows_svg_attribute_names_that_contain_on_prefix(self):
        self.assert_asset_valid(
            "safe-data-attribute.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg' data-onload='label'></svg>",
        )

    def test_rejects_invalid_office_zip(self):
        self.assert_asset_invalid("bad.docx", b"not a zip file")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types></Types>")
            archive.writestr("not-word/document.xml", "<xml></xml>")
        self.assert_asset_invalid("bad-root.docx", buffer.getvalue())

    def test_rejects_oversize_asset(self):
        asset = CMSAsset(
            name="Too Large",
            file=uploaded_file("too-large.txt", b"x" * (MAX_ASSET_UPLOAD_BYTES + 1), "text/plain"),
        )

        with self.assertRaises(ValidationError) as ctx:
            asset.full_clean()

        self.assertIn("20 MB", str(ctx.exception))

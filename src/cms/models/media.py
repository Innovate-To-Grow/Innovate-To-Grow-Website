"""Media models and helpers for CMS-managed assets."""

import io
import os
import re
import zipfile

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from core.models import ProjectControlModel

IMAGE_ASSET_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "svg"]
DOCUMENT_ASSET_EXTENSIONS = ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "txt"]
ALLOWED_ASSET_EXTENSIONS = [*IMAGE_ASSET_EXTENSIONS, *DOCUMENT_ASSET_EXTENSIONS]
MAX_ASSET_UPLOAD_BYTES = 20 * 1024 * 1024

# Magic-byte signatures for allowed file types
_OFFICE_OOXML_ROOTS = {
    "docx": "word/",
    "xlsx": "xl/",
    "pptx": "ppt/",
}
_OLE_COMPOUND_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_SVG_EVENT_HANDLER_RE = re.compile(rb"\son[a-z0-9_-]+\s*=", re.IGNORECASE)


def _asset_extension(file):
    _, ext = os.path.splitext(getattr(file, "name", "") or "")
    return ext.lstrip(".").lower()


def _read_file(file):
    file.seek(0)
    try:
        content = file.read()
    finally:
        file.seek(0)
    return content.encode() if isinstance(content, str) else content


def _read_header(file, size=8192):
    file.seek(0)
    try:
        header = file.read(size)
    finally:
        file.seek(0)
    return header.encode() if isinstance(header, str) else header


def validate_asset_file_size(file):
    """Limit CMS uploads to a bounded size for admin UX and storage safety."""
    size = getattr(file, "size", None)
    if size is not None and size > MAX_ASSET_UPLOAD_BYTES:
        raise ValidationError("CMS asset uploads must be 20 MB or smaller.")


def validate_asset_file_type(file):
    """Validate uploaded file content against the extension-specific allowlist."""
    ext = _asset_extension(file)
    header = _read_header(file)

    if ext == "png" and header.startswith(b"\x89PNG"):
        return
    if ext in {"jpg", "jpeg"} and header.startswith(b"\xff\xd8\xff"):
        return
    if ext == "gif" and header.startswith((b"GIF87a", b"GIF89a")):
        return
    if ext == "webp" and header[:4] == b"RIFF" and len(header) >= 12 and header[8:12] == b"WEBP":
        return
    if ext == "pdf" and header.startswith(b"%PDF"):
        return

    if ext == "svg":
        _validate_svg_asset(file)
        return

    if ext in _OFFICE_OOXML_ROOTS:
        _validate_ooxml_asset(file, ext)
        return

    if ext in {"doc", "xls", "ppt"} and header.startswith(_OLE_COMPOUND_SIGNATURE):
        return

    if ext in {"csv", "txt"}:
        _validate_text_asset(file)
        return

    raise ValidationError("File type not allowed. Upload an approved image, PDF, Office document, CSV, or text file.")


def _validate_svg_asset(file):
    content = _read_file(file)
    stripped = content.lstrip()
    if stripped.startswith(b"\xef\xbb\xbf"):
        stripped = stripped[3:].lstrip()
    if not stripped.startswith((b"<?xml", b"<svg")) and b"<svg" not in stripped[:512].lower():
        raise ValidationError("SVG file content is invalid.")

    lowered = content.lower()
    if b"<script" in lowered or b"javascript:" in lowered or _SVG_EVENT_HANDLER_RE.search(content):
        raise ValidationError("SVG contains scripts or inline event handlers and was rejected as unsafe.")


def _validate_ooxml_asset(file, ext):
    content = _read_file(file)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise ValidationError(f"{ext.upper()} file content is invalid.") from exc

    root = _OFFICE_OOXML_ROOTS[ext]
    if "[Content_Types].xml" not in names or not any(name.startswith(root) for name in names):
        raise ValidationError(f"{ext.upper()} file content is invalid.")


def _validate_text_asset(file):
    content = _read_file(file)
    if b"\x00" in content:
        raise ValidationError("Text asset contains binary data.")
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("Text assets must be UTF-8 encoded.") from exc


def asset_upload_path(instance, filename):
    """Store uploaded CMS assets under a stable media prefix."""
    _, ext = os.path.splitext(filename or "")
    asset_id = getattr(instance, "id", None) or "unassigned"
    return os.path.join("cms", "assets", str(asset_id), f"asset{ext.lower()}")


class CMSAsset(ProjectControlModel):
    """Reusable uploaded asset for CMS editors."""

    name = models.CharField(max_length=200)
    file = models.FileField(
        upload_to=asset_upload_path,
        validators=[
            FileExtensionValidator(ALLOWED_ASSET_EXTENSIONS),
            validate_asset_file_size,
            validate_asset_file_type,
        ],
    )

    class Meta:
        db_table = "cms_cmsasset"
        ordering = ["name", "created_at"]
        verbose_name = "CMS Asset"
        verbose_name_plural = "CMS Assets"

    def __str__(self):
        return self.name

    @property
    def public_url(self):
        if not self.file:
            return ""
        return self.file.url

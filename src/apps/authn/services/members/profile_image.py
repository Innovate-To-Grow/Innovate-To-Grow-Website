"""Profile-image validation and encoding.

``Member.profile_image`` is a ``TextField`` holding a base64 ``data:`` URI rather than an
``ImageField``, so every write path has to validate and encode by hand. This module is the single
source of truth for that, shared by the admin change form
(``apps.authn.admin.members.forms.MemberChangeForm``) and the account API
(``apps.authn.views.account.profile.ProfileView``) — before, the API enforced a size cap, a
content-type allow-list and a magic-byte check while the admin enforced nothing but an HTML
``accept`` attribute.

Uploads are downscaled before encoding: the stored string is inlined in API responses and read by
every changelist/export query, so an un-resized 5 MB photo becomes ~6.8 MB of text on the row.
"""

import base64
import binascii
import io
import logging

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024

# Content types accepted from the client, and the magic-byte signature each must actually start
# with. The stored MIME is always derived from the verified signature, never from the client's
# ``Content-Type`` header, so a crafted multipart part cannot smuggle ``text/html`` into the
# ``data:`` URI.
ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
_SIGNATURES = (
    (b"\x89PNG", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
    (b"RIFF", "image/webp"),
)

# Pillow format to encode each verified MIME back to after downscaling.
_PILLOW_FORMATS = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/gif": "GIF",
    "image/webp": "WEBP",
}

MAX_DIMENSION = 512

OVERSIZE_ERROR = "Profile image must be 5 MB or smaller."
CONTENT_TYPE_ERROR = "Profile image must be a JPEG, PNG, GIF, or WebP file."
SIGNATURE_ERROR = "File content does not match an allowed image type (JPEG, PNG, GIF, WebP)."


class ProfileImageError(ValueError):
    """An uploaded profile image was rejected. ``str(exc)`` is safe to show the user."""


def detect_image_mime(data: bytes) -> str | None:
    """Return the MIME type implied by ``data``'s magic bytes, or None if unrecognised."""
    for signature, mime in _SIGNATURES:
        if data.startswith(signature):
            return mime
    return None


def validate_profile_image(upload) -> tuple[bytes, str]:
    """Validate an uploaded file and return ``(raw_bytes, verified_mime)``.

    Raises ``ProfileImageError`` when the upload is too large, declares a disallowed content type,
    or does not actually start with an allowed image signature.
    """
    size = getattr(upload, "size", None)
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise ProfileImageError(OVERSIZE_ERROR)

    declared = (getattr(upload, "content_type", "") or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_CONTENT_TYPES:
        raise ProfileImageError(CONTENT_TYPE_ERROR)

    # ``value_from_datadict`` may already have consumed the stream, and it runs more than once per
    # request, so never assume the cursor is at the start.
    _rewind(upload)
    raw = upload.read()
    _rewind(upload)

    if size is None and len(raw) > MAX_UPLOAD_BYTES:
        raise ProfileImageError(OVERSIZE_ERROR)

    mime = detect_image_mime(raw[:32])
    if mime is None:
        raise ProfileImageError(SIGNATURE_ERROR)
    return raw, mime


def build_profile_image_data_uri(raw: bytes, mime: str, *, max_dimension: int = MAX_DIMENSION) -> str:
    """Downscale ``raw`` to ``max_dimension`` and return it as a base64 ``data:`` URI."""
    resized = _downscale(raw, mime, max_dimension)
    encoded = base64.b64encode(resized).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def encode_profile_image(upload, *, max_dimension: int = MAX_DIMENSION) -> str:
    """Validate ``upload`` and return the ``data:`` URI to store on ``Member.profile_image``."""
    raw, mime = validate_profile_image(upload)
    return build_profile_image_data_uri(raw, mime, max_dimension=max_dimension)


def split_data_uri(value: str) -> tuple[bytes, str]:
    """Split a stored ``profile_image`` into ``(raw_bytes, mime)``.

    Tolerates the bare-base64 values that predate the ``data:`` prefix (see
    ``apps.authn.serializers.account.profile``). Raises ``ProfileImageError`` if the payload is not
    decodable, so callers can answer 404 rather than 500.
    """
    header, separator, payload = (value or "").partition(",")
    mime = "application/octet-stream"
    if separator and header.startswith("data:"):
        declared = header[len("data:") :].split(";")[0].strip().lower()
        mime = declared or "application/octet-stream"
    else:
        payload = value or ""

    try:
        raw = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ProfileImageError("Stored profile image is not valid base64.") from exc
    if not raw:
        raise ProfileImageError("Stored profile image is empty.")

    # Prefer what the bytes actually are over what the stored header claims.
    return raw, detect_image_mime(raw[:32]) or mime


def _rewind(upload) -> None:
    try:
        upload.seek(0)
    except (AttributeError, OSError, ValueError):
        pass


def _downscale(raw: bytes, mime: str, max_dimension: int) -> bytes:
    """Return ``raw`` resized so neither side exceeds ``max_dimension``.

    Falls back to the original bytes when Pillow cannot handle the image — validation has already
    confirmed the signature, so a decode failure should not block the save.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a hard requirement
        return raw

    pillow_format = _PILLOW_FORMATS.get(mime)
    if pillow_format is None:
        return raw

    try:
        with Image.open(io.BytesIO(raw)) as image:
            if max(image.size) <= max_dimension:
                return raw
            if getattr(image, "is_animated", False):
                # Resizing would flatten the animation; keep the original.
                return raw
            image.thumbnail((max_dimension, max_dimension))
            if pillow_format == "JPEG" and image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format=pillow_format)
            return buffer.getvalue()
    except (OSError, ValueError):
        logger.warning("Could not downscale profile image (%s); storing the original.", mime)
        return raw

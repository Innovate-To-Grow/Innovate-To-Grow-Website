"""
Shared I2G email layout — wraps content in the branded header/footer template.

Used by:
- SES Compose admin (admin-composed emails)
- Ticket emails (event registration)
- Auth code emails (registration, login, password reset)
- Invitation emails (admin invitations)
"""

import base64
import logging
from functools import lru_cache
from pathlib import Path

from django.contrib.staticfiles import finders

logger = logging.getLogger(__name__)

_LOGO_CID = "i2g-logo"
_LOGO_FILENAME = "i2glogo.png"
_LOGO_STATIC_PATH = "images/i2glogo.png"


def _find_logo_path() -> Path | None:
    """Locate the I2G logo via Django staticfiles finders."""
    result = finders.find(_LOGO_STATIC_PATH)
    if result:
        return Path(result)
    return None


@lru_cache(maxsize=1)
def _read_logo_bytes() -> bytes:
    """Read and cache the logo file bytes."""
    path = _find_logo_path()
    if path is None:
        logger.warning("I2G logo not found at static path: %s", _LOGO_STATIC_PATH)
        return b""
    return path.read_bytes()


def get_logo_inline_image() -> tuple[str, str, bytes]:
    """Return the logo as a CID inline image tuple for SES.

    Returns:
        (cid, filename, bytes) — pass to SESService.send_message(inline_images=[...])
    """
    return (_LOGO_CID, _LOGO_FILENAME, _read_logo_bytes())


def get_logo_data_uri() -> str:
    """Return the logo as a data URI for browser preview rendering."""
    logo_bytes = _read_logo_bytes()
    if not logo_bytes:
        return ""
    encoded = base64.b64encode(logo_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_email_layout(content_html: str, *, logo_src: str = f"cid:{_LOGO_CID}") -> str:
    """Wrap inner content HTML in the I2G branded email layout.

    Args:
        content_html: The email body content (already escaped/safe HTML).
        logo_src: Image src for the logo. Defaults to ``cid:i2g-logo`` for real
            emails. Pass a data URI (from ``get_logo_data_uri()``) for browser preview.

    Returns:
        Complete email HTML string with header, content, and footer.
    """
    logo_img = ""
    if logo_src:
        logo_img = (
            f'<img src="{logo_src}" alt="Innovate to Grow" '
            f'style="width:80px;height:80px;border-radius:50%;margin-bottom:8px;">'
        )

    return f"""\
<div style="font-family:Arial,sans-serif;line-height:1.6;color:#111827;max-width:640px;margin:0 auto;">
  <div style="text-align:center;padding:24px 0 16px;">
    {logo_img}
    <span style="display:block;font-size:28px;font-weight:800;color:#1e3a5f;letter-spacing:0.02em;">Innovate to Grow</span>
    <span style="display:block;font-size:13px;color:#6b7280;margin-top:2px;">UC Merced</span>
  </div>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 24px;">
  {content_html}
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0 16px;">
  <p style="font-size:12px;color:#9ca3af;text-align:center;">Innovate to Grow &mdash; UC Merced</p>
</div>"""

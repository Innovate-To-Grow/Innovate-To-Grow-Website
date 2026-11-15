"""Where the short ``/register`` link (and its QR code) sends people: Mail → SMS Settings, "/register leads to".

The SPA's ``/register`` page asks ``GET /mail/register-link/`` and goes there. The answer is cached briefly and
dropped when the settings are saved; a value that is not a safe page on this site falls back to the sign-in page,
which takes an email address or a phone number and creates the account.
"""

import io

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from apps.mail.models import SmsConfig
from apps.mail.models.sms_config import DEFAULT_REGISTER_PATH, REGISTER_PATH, register_path_errors

CACHE_KEY = "mail:sms:register-link"
CACHE_SECONDS = 300
# Pixels per QR module: the SVG scales freely, the PNG is large enough to print.
QR_KINDS = {"svg": 10, "png": 12}


def register_destination() -> str:
    path = cache.get(CACHE_KEY)
    if path is None:
        configured = (SmsConfig.load().register_redirect_path or "").strip()
        path = DEFAULT_REGISTER_PATH if register_path_errors(configured) else configured
        cache.set(CACHE_KEY, path, CACHE_SECONDS)
    return path


def register_url() -> str:
    """The absolute short link the QR code holds."""
    frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    return f"{frontend_url}{REGISTER_PATH}" if frontend_url else ""


def forget_register_destination(**kwargs) -> None:
    """``post_save`` of ``SmsConfig``: drop the cached answer once the change commits."""
    transaction.on_commit(lambda: cache.delete(CACHE_KEY))


def register_qr(kind: str) -> bytes:
    """The QR code of ``register_url()`` for flyers and slides: ``"svg"`` or ``"png"`` (ValueError without a
    FRONTEND_URL, or for another kind)."""
    import segno

    url = register_url()
    if not url or kind not in QR_KINDS:
        raise ValueError("The QR code needs FRONTEND_URL and a kind of svg or png.")
    buffer = io.BytesIO()
    # Error level M survives a smudge or a fold; a 4-module quiet zone is what scanners expect.
    segno.make(url, error="m", micro=False).save(buffer, kind=kind, scale=QR_KINDS[kind], border=4)
    return buffer.getvalue()

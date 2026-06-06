import base64
import secrets
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin

from django.conf import settings
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import crypto, timezone
from pdf417gen import encode, render_image

from apps.event.models import EventRegistration

_TICKET_TOKEN_SALT = "event-ticket-access"
_TICKET_LOGIN_SALT = "event-ticket-login"
_TICKET_ACCESS_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
_TICKET_LOGIN_MAX_AGE = 60 * 60 * 24  # 24 hours


class TicketLoginTokenError(ValueError):
    """Base error for invalid ticket login tokens."""


def build_ticket_access_token(registration: EventRegistration) -> str:
    return signing.dumps({"registration_id": str(registration.pk)}, salt=_TICKET_TOKEN_SALT, compress=True)


def get_registration_from_access_token(token: str) -> EventRegistration:
    try:
        payload = signing.loads(token, salt=_TICKET_TOKEN_SALT, max_age=_TICKET_ACCESS_MAX_AGE)
        registration_id = payload["registration_id"]
    except signing.BadSignature as exc:
        raise ValueError("Invalid ticket access token.") from exc

    try:
        return EventRegistration.objects.select_related("event", "ticket", "member").get(pk=registration_id)
    except ObjectDoesNotExist as exc:
        raise ValueError("Ticket not found.") from exc


def _hash_ticket_login_nonce(nonce: str) -> str:
    return crypto.salted_hmac(_TICKET_LOGIN_SALT, nonce).hexdigest()


def build_ticket_login_token(registration: EventRegistration) -> str:
    """Create a one-time signed login token for a ticket email."""
    nonce = secrets.token_urlsafe(32)
    registration.ticket_login_token_hash = _hash_ticket_login_nonce(nonce)
    registration.ticket_login_token_sent_at = timezone.now()
    registration.ticket_login_token_used_at = None
    registration.save(
        update_fields=[
            "ticket_login_token_hash",
            "ticket_login_token_sent_at",
            "ticket_login_token_used_at",
            "updated_at",
        ]
    )
    return signing.dumps(
        {
            "registration_id": str(registration.pk),
            "member_id": str(registration.member_id),
            "nonce": nonce,
        },
        salt=_TICKET_LOGIN_SALT,
        compress=True,
    )


def get_member_from_login_token(token: str):
    """Validate and consume a one-time ticket login token."""
    try:
        payload = signing.loads(token, salt=_TICKET_LOGIN_SALT, max_age=_TICKET_LOGIN_MAX_AGE)
        registration_id = payload["registration_id"]
        member_id = payload["member_id"]
        nonce = payload["nonce"]
    except (KeyError, signing.BadSignature) as exc:
        raise TicketLoginTokenError("Invalid or expired login link.") from exc

    try:
        with transaction.atomic():
            registration = (
                EventRegistration.objects.select_for_update()
                .select_related("member")
                .get(pk=registration_id, member_id=member_id)
            )
            expected_hash = _hash_ticket_login_nonce(nonce)
            if (
                not registration.member.is_active
                or not registration.ticket_login_token_hash
                or registration.ticket_login_token_used_at is not None
                or not crypto.constant_time_compare(registration.ticket_login_token_hash, expected_hash)
            ):
                raise TicketLoginTokenError("Invalid or expired login link.")

            registration.ticket_login_token_hash = ""  # nosec B105 — clears the consumed token hash, not a password
            registration.ticket_login_token_used_at = timezone.now()
            registration.save(update_fields=["ticket_login_token_hash", "ticket_login_token_used_at", "updated_at"])
            return registration.member
    except ObjectDoesNotExist as exc:
        raise TicketLoginTokenError("Invalid or expired login link.") from exc


def build_backend_absolute_url(path: str, request=None) -> str:
    if request is not None:
        return request.build_absolute_uri(path)

    base_url = (getattr(settings, "BACKEND_URL", "") or "").strip().rstrip("/")
    if not base_url:
        base_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    if not base_url:
        return path
    return urljoin(f"{base_url}/", path.lstrip("/"))


def build_frontend_absolute_url(path: str, request=None) -> str:
    base_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    if base_url:
        return urljoin(f"{base_url}/", path.lstrip("/"))
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def generate_ticket_barcode_png_bytes(registration: EventRegistration) -> bytes:
    codes = encode(registration.barcode_payload, columns=4)
    image = render_image(codes, scale=4, ratio=3, padding=10)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_ticket_barcode_data_url(registration: EventRegistration) -> str:
    payload = base64.b64encode(generate_ticket_barcode_png_bytes(registration)).decode("ascii")
    return f"data:image/png;base64,{payload}"


def get_event_datetime(event) -> datetime:
    event_dt = datetime.combine(event.date, datetime.min.time())
    if timezone.is_naive(event_dt):
        return timezone.make_aware(event_dt, timezone.get_current_timezone())
    return event_dt

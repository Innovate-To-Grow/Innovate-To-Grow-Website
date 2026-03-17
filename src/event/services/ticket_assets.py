import base64
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin

from django.conf import settings
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from pdf417gen import encode, render_image

from event.models import EventRegistration

_TICKET_TOKEN_SALT = "event-ticket-access"


def build_ticket_access_token(registration: EventRegistration) -> str:
    return signing.dumps({"registration_id": str(registration.pk)}, salt=_TICKET_TOKEN_SALT, compress=True)


def get_registration_from_access_token(token: str) -> EventRegistration:
    try:
        payload = signing.loads(token, salt=_TICKET_TOKEN_SALT)
        registration_id = payload["registration_id"]
    except signing.BadSignature as exc:
        raise ValueError("Invalid ticket access token.") from exc

    try:
        return EventRegistration.objects.select_related("event", "ticket", "member").get(pk=registration_id)
    except ObjectDoesNotExist as exc:
        raise ValueError("Ticket not found.") from exc


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
    codes = encode(registration.barcode_payload, columns=6)
    image = render_image(codes, scale=3, ratio=3, padding=10)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_ticket_barcode_data_url(registration: EventRegistration) -> str:
    payload = base64.b64encode(generate_ticket_barcode_png_bytes(registration)).decode("ascii")
    return f"data:image/png;base64,{payload}"


def get_event_datetime(event) -> datetime:
    event_dt = datetime.combine(event.date, event.time)
    if timezone.is_naive(event_dt):
        return timezone.make_aware(event_dt, timezone.get_current_timezone())
    return event_dt

"""
Registration flow helpers for event registration APIs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.utils import timezone

from authn.models import ContactEmail, Member
from notify.models import VerificationRequest
from notify.services import VerificationError, verify_link

from ..models import Event, EventRegistration


class EventRegistrationFlowError(Exception):
    """Domain error carrying a stable code for API responses."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def get_live_event() -> Event:
    event = Event.objects.filter(is_live=True).order_by("-updated_at", "-created_at").first()
    if not event:
        raise EventRegistrationFlowError("no_live_event", "No live event found.")
    return event


def resolve_member_by_email(email: str) -> Member | None:
    normalized = email.strip().lower()
    member = Member.objects.filter(email__iexact=normalized).first()
    if member:
        return member

    member = Member.objects.filter(account_email__email_address__iexact=normalized).first()
    if member:
        return member

    contact = ContactEmail.objects.filter(email_address__iexact=normalized).first()
    if not contact:
        return None

    # Fallback: use reverse relation through account_email when possible.
    return Member.objects.filter(account_email=contact).first()


@dataclass(frozen=True)
class RegistrationTokenContext:
    event: Event
    member: Member
    registration: EventRegistration
    verification: VerificationRequest


def get_registration_from_token(token: str, *, verify_token: bool = True) -> RegistrationTokenContext:
    normalized_token = token.strip()
    if not normalized_token:
        raise EventRegistrationFlowError("invalid_token", "Token is required.")

    verification = (
        VerificationRequest.objects.filter(
            token=normalized_token,
            method=VerificationRequest.METHOD_LINK,
            purpose="event_registration_link",
        )
        .order_by("-created_at")
        .first()
    )
    if not verification:
        raise EventRegistrationFlowError("invalid_token", "Invalid registration token.")

    if verify_token:
        try:
            verify_link(token=normalized_token, purpose="event_registration_link")
        except VerificationError as exc:
            raise EventRegistrationFlowError("invalid_token", str(exc)) from exc

    event = get_live_event()
    member = resolve_member_by_email(verification.target)
    if not member:
        raise EventRegistrationFlowError(
            "member_not_found",
            "No member account is associated with this email. Complete membership registration first.",
        )

    registration, _ = EventRegistration.objects.get_or_create(
        event=event,
        member=member,
        defaults={
            "source_email": verification.target.lower(),
            "status": EventRegistration.STATUS_PENDING,
        },
    )
    if registration.registration_token != normalized_token:
        registration.registration_token = normalized_token
        registration.source_email = verification.target.lower()
        registration.save(update_fields=["registration_token", "source_email", "updated_at"])

    return RegistrationTokenContext(
        event=event,
        member=member,
        registration=registration,
        verification=verification,
    )


def normalize_phone(phone_number: str, phone_region: str = "") -> str:
    """
    Normalize to E.164-ish string with leading +.
    """
    raw = (phone_number or "").strip()
    if not raw:
        return ""

    if raw.startswith("+"):
        return "+" + re.sub(r"\D", "", raw)

    region = (phone_region or "").strip() or "1-US"
    country_code = region.split("-")[0]
    local_digits = re.sub(r"\D", "", raw)
    return f"+{country_code}{local_digits}"


def build_registration_snapshot(
    *,
    primary_email: str,
    secondary_email: str,
    phone_number: str,
    answers: list[dict],
) -> dict:
    return {
        "primary_email": primary_email,
        "secondary_email": secondary_email,
        "phone_number": phone_number,
        "answers": answers,
        "saved_at": timezone.now().isoformat(),
    }

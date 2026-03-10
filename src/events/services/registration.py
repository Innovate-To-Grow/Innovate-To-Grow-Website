"""
Registration flow helpers for event registration APIs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.utils import timezone

from authn.models import ContactEmail, Member

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

    contact = ContactEmail.objects.filter(email_address__iexact=normalized, member__isnull=False).first()
    if contact:
        return contact.member

    return None


@dataclass(frozen=True)
class RegistrationTokenContext:
    event: Event
    member: Member
    registration: EventRegistration


def get_registration_from_token(token: str) -> RegistrationTokenContext:
    normalized_token = token.strip()
    if not normalized_token:
        raise EventRegistrationFlowError("invalid_token", "Token is required.")

    registration = EventRegistration.objects.filter(registration_token=normalized_token).order_by("-created_at").first()
    if not registration:
        raise EventRegistrationFlowError("invalid_token", "Invalid registration token.")

    event = get_live_event()
    member = registration.member
    if not member:
        raise EventRegistrationFlowError(
            "member_not_found",
            "No member account is associated with this registration.",
        )

    return RegistrationTokenContext(
        event=event,
        member=member,
        registration=registration,
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

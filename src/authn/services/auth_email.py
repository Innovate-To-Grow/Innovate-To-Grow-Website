"""
Helpers for resolving which email addresses are eligible for auth flows.
"""

from dataclasses import dataclass

from django.contrib.auth import get_user_model

from authn.models import ContactEmail

Member = get_user_model()


@dataclass(frozen=True)
class ResolvedAuthEmail:
    member: Member
    delivery_email: str
    source_type: str


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def resolve_auth_email(email: str, *, require_active: bool = True) -> ResolvedAuthEmail | None:
    normalized = normalize_email(email)
    if not normalized:
        return None

    member = Member.objects.filter(email__iexact=normalized).first()
    if member and (member.is_active or not require_active):
        return ResolvedAuthEmail(member=member, delivery_email=normalized, source_type="member")

    contact = (
        ContactEmail.objects.select_related("member")
        .filter(email_address__iexact=normalized, verified=True)
        .first()
    )
    if contact and contact.member and (contact.member.is_active or not require_active):
        return ResolvedAuthEmail(member=contact.member, delivery_email=normalized, source_type="contact")

    return None


def get_member_auth_emails(member: Member) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()

    def add(email_value: str):
        normalized = normalize_email(email_value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            emails.append(normalized)

    add(member.email)
    contacts = ContactEmail.objects.filter(member=member, verified=True).order_by("email_type", "created_at")
    for contact in contacts:
        add(contact.email_address)

    return emails


def registration_email_conflicts(email: str, *, exclude_member_id=None) -> bool:
    normalized = normalize_email(email)
    member_qs = Member.objects.filter(email__iexact=normalized)
    if exclude_member_id:
        member_qs = member_qs.exclude(pk=exclude_member_id)
    if member_qs.exists():
        return True
    return ContactEmail.objects.filter(email_address__iexact=normalized).exists()

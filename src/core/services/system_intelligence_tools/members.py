from typing import Any

from django.db.models import Count

from core.services.system_intelligence_actions.exceptions import ActionRequestError

from .query_helpers import bounded_limit, object_payload, queryset_payload, require_one
from .runtime import run_action_service_async

MEMBER_FIELDS = [
    "id",
    "first_name",
    "last_name",
    "middle_name",
    "organization",
    "title",
    "is_active",
    "date_joined",
    "created_at",
    "updated_at",
]


async def get_member_detail(member_id: str | None = None, email: str | None = None) -> dict[str, Any]:
    """Get a member profile with contact emails, phones, and high-level counts."""
    return await run_action_service_async(_get_member_detail, member_id, email)


async def search_contact_info(
    email: str | None = None,
    phone: str | None = None,
    subscribed: bool | None = None,
    verified: bool | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Search saved contact emails and phone numbers by value, subscription, or verification state."""
    return await run_action_service_async(_search_contact_info, email, phone, subscribed, verified, limit)


async def get_member_activity_summary(member_id: str | None = None, email: str | None = None) -> dict[str, Any]:
    """Summarize a member's registrations, email campaign deliveries, and page-view activity."""
    return await run_action_service_async(_get_member_activity_summary, member_id, email)


def _find_member(member_id: str | None = None, email: str | None = None):
    from authn.models import Member

    qs = Member.objects.prefetch_related("contact_emails", "contact_phones")
    if member_id:
        return require_one(qs.filter(pk=member_id), "Member")
    if email:
        return require_one(qs.filter(contact_emails__email_address__iexact=email).distinct(), "Member")
    raise ActionRequestError("Provide member_id or email.")


def _get_member_detail(member_id: str | None = None, email: str | None = None) -> dict[str, Any]:
    from mail.models import RecipientLog

    member = _find_member(member_id, email)
    emails = [
        object_payload(item, ["id", "email_address", "email_type", "subscribe", "verified", "created_at"])
        for item in member.contact_emails.all()
    ]
    phones = [
        object_payload(item, ["id", "phone_number", "region", "subscribe", "verified", "created_at"])
        for item in member.contact_phones.all()
    ]
    return {
        "member": object_payload(member, MEMBER_FIELDS),
        "primary_email": member.get_primary_email(),
        "contact_emails": emails,
        "contact_phones": phones,
        "counts": {
            "event_registrations": member.event_registrations.count(),
            "campaign_recipient_logs": RecipientLog.objects.filter(member=member).count(),
            "page_views": member.page_views.count(),
        },
    }


def _search_contact_info(
    email: str | None = None,
    phone: str | None = None,
    subscribed: bool | None = None,
    verified: bool | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    from authn.models import ContactEmail, ContactPhone

    row_limit = bounded_limit(limit)
    email_qs = ContactEmail.objects.select_related("member")
    phone_qs = ContactPhone.objects.select_related("member")
    if email:
        email_qs = email_qs.filter(email_address__icontains=email)
        if not phone:
            phone_qs = phone_qs.none()
    if phone:
        phone_qs = phone_qs.filter(phone_number__icontains=phone)
        if not email:
            email_qs = email_qs.none()
    if subscribed is not None:
        email_qs = email_qs.filter(subscribe=subscribed)
        phone_qs = phone_qs.filter(subscribe=subscribed)
    if verified is not None:
        email_qs = email_qs.filter(verified=verified)
        phone_qs = phone_qs.filter(verified=verified)
    return {
        "emails": queryset_payload(
            email_qs.order_by("-created_at"),
            ["id", "member_id", "email_address", "email_type", "subscribe", "verified", "created_at"],
            limit=row_limit,
        ),
        "phones": queryset_payload(
            phone_qs.order_by("-created_at"),
            ["id", "member_id", "phone_number", "region", "subscribe", "verified", "created_at"],
            limit=row_limit,
        ),
    }


def _get_member_activity_summary(member_id: str | None = None, email: str | None = None) -> dict[str, Any]:
    from cms.models import PageView
    from event.models import EventRegistration
    from mail.models import RecipientLog

    member = _find_member(member_id, email)
    registrations = EventRegistration.objects.filter(member=member).select_related("event", "ticket")
    recipient_logs = RecipientLog.objects.filter(member=member)
    page_views = PageView.objects.filter(member=member)
    delivery_breakdown = list(recipient_logs.values("status").annotate(count=Count("id")).order_by("status"))
    return {
        "member": object_payload(member, ["id", "first_name", "last_name", "organization", "title", "is_active"]),
        "registration_count": registrations.count(),
        "recent_registrations": queryset_payload(
            registrations.order_by("-created_at"),
            ["id", "event__name", "ticket__name", "attendee_email", "created_at"],
            limit=10,
        )["rows"],
        "campaign_delivery_breakdown": delivery_breakdown,
        "page_view_count": page_views.count(),
        "recent_page_views": queryset_payload(page_views.order_by("-timestamp"), ["path", "timestamp"], limit=10)[
            "rows"
        ],
    }

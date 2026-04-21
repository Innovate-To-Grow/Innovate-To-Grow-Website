"""Resolve campaign audience to a list of recipient dicts."""

from authn.models import Member
from event.models import EventRegistration


def get_recipients(campaign):
    """
    Return a deduplicated list of recipient dicts for the given campaign.

    Each dict contains: member_id, email, first_name, last_name, full_name.
    """
    send_all = campaign.member_email_scope == "all"
    recipients = _recipients_for_audience(
        campaign.audience_type,
        send_all=send_all,
        event=campaign.event,
        ticket_uuid_str=campaign.manual_emails.strip() if campaign.audience_type == "ticket_type" else "",
        selected_members=campaign.selected_members,
        manual_emails_body=campaign.manual_emails if campaign.audience_type == "manual" else "",
    )

    exclude_type = (campaign.exclude_audience_type or "").strip()
    if exclude_type:
        excluded = _recipients_for_audience(
            exclude_type,
            send_all=send_all,
            event=campaign.exclude_event,
            ticket_uuid_str=campaign.exclude_ticket_id.strip() if exclude_type == "ticket_type" else "",
            selected_members=campaign.exclude_members,
            manual_emails_body="",
        )
        exclude_emails = {r["email"].lower() for r in excluded if r.get("email")}
        recipients = [r for r in recipients if r.get("email") and r["email"].lower() not in exclude_emails]

    return recipients


def _recipients_for_audience(
    audience_type: str,
    *,
    send_all: bool,
    event,
    ticket_uuid_str: str,
    selected_members,
    manual_emails_body: str,
):
    """Resolve one audience_type to recipient dicts (shared by primary and exclusion)."""
    dispatch = {
        "subscribers": lambda: _subscribers(send_all),
        "event_registrants": lambda: _event_registrants(event),
        "ticket_type": lambda: _ticket_type_for_event(event, ticket_uuid_str),
        "checked_in": lambda: _checked_in(event),
        "not_checked_in": lambda: _not_checked_in(event),
        "all_members": lambda: _all_members(send_all),
        "staff": lambda: _staff(send_all),
        "selected_members": lambda: _selected_members_from(selected_members, send_all),
        "manual": lambda: _manual_emails_from_body(manual_emails_body),
    }
    resolver = dispatch.get(audience_type)
    return resolver() if resolver else []


def _subscribers(send_all=False):
    members = (
        Member.objects.filter(contact_emails__subscribe=True, contact_emails__email_type="primary")
        .distinct()
        .prefetch_related("contact_emails")
        .order_by("first_name", "last_name")
    )
    return _members_to_recipients(members, send_all=send_all)


def _event_registrants(event):
    if not event:
        return []
    registrations = (
        EventRegistration.objects.filter(event=event)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return _registrations_to_recipients(registrations)


def _selected_members_from(selected_members, send_all):
    members = selected_members.prefetch_related("contact_emails").order_by("first_name", "last_name")
    return _members_to_recipients(members, send_all=send_all)


def _manual_emails_from_body(body: str):
    recipients = []
    seen = set()
    for line in (body or "").strip().splitlines():
        email = line.strip()
        if not email or email in seen:
            continue
        seen.add(email)
        recipients.append(
            {
                "member_id": None,
                "email": email,
                "first_name": "",
                "last_name": "",
                "full_name": "",
            }
        )
    return recipients


def _ticket_type_for_event(event, ticket_id: str):
    """Registrants for a specific event + ticket type."""
    if not event or not ticket_id:
        return []
    registrations = (
        EventRegistration.objects.filter(event=event, ticket_id=ticket_id)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return _registrations_to_recipients(registrations)


def _checked_in(event):
    """Registrants who have at least one check-in record for the event."""
    from event.models import CheckInRecord

    if not event:
        return []
    checked_reg_ids = CheckInRecord.objects.filter(check_in__event=event).values_list("registration_id", flat=True)
    registrations = (
        EventRegistration.objects.filter(event=event, pk__in=checked_reg_ids)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return _registrations_to_recipients(registrations)


def _not_checked_in(event):
    """Registrants with no check-in record for the event (no-shows)."""
    from event.models import CheckInRecord

    if not event:
        return []
    checked_reg_ids = CheckInRecord.objects.filter(check_in__event=event).values_list("registration_id", flat=True)
    registrations = (
        EventRegistration.objects.filter(event=event)
        .exclude(pk__in=checked_reg_ids)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return _registrations_to_recipients(registrations)


def _all_members(send_all=False):
    """All active members with a primary email."""
    members = (
        Member.objects.filter(is_active=True).prefetch_related("contact_emails").order_by("first_name", "last_name")
    )
    return _members_to_recipients(members, send_all=send_all)


def _staff(send_all=False):
    """Staff members (is_staff=True) with a primary email."""
    members = (
        Member.objects.filter(is_staff=True, is_active=True)
        .prefetch_related("contact_emails")
        .order_by("first_name", "last_name")
    )
    return _members_to_recipients(members, send_all=send_all)


# -- helpers -----------------------------------------------------------------


def _registrations_to_recipients(registrations):
    """Convert an EventRegistration queryset to deduplicated recipient dicts."""
    seen = set()
    recipients = []
    for reg in registrations:
        email = reg.attendee_email or reg.member.get_primary_email()
        if not email or email in seen:
            continue
        seen.add(email)
        first = reg.attendee_first_name or reg.member.first_name or ""
        last = reg.attendee_last_name or reg.member.last_name or ""
        recipients.append(
            {
                "member_id": reg.member_id,
                "email": email,
                "first_name": first,
                "last_name": last,
                "full_name": f"{first} {last}".strip(),
            }
        )
    return recipients


def _members_to_recipients(members, *, send_all=False):
    """Convert a Member queryset to deduplicated recipient dicts."""
    seen = set()
    recipients = []
    for member in members:
        if send_all:
            emails = [ce.email_address for ce in member.contact_emails.all() if ce.email_address]
        else:
            primary = member.get_primary_email()
            emails = [primary] if primary else []
        for email in emails:
            if not email or email in seen:
                continue
            seen.add(email)
            recipients.append(
                {
                    "member_id": member.id,
                    "email": email,
                    "first_name": member.first_name or "",
                    "last_name": member.last_name or "",
                    "full_name": member.get_full_name(),
                }
            )
    return recipients

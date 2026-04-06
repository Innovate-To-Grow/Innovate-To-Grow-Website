"""Resolve campaign audience to a list of recipient dicts."""

from authn.models import Member
from event.models import EventRegistration


def get_recipients(campaign):
    """
    Return a deduplicated list of recipient dicts for the given campaign.

    Each dict contains: member_id, email, first_name, last_name, full_name.
    """
    dispatch = {
        "subscribers": lambda: _subscribers(),
        "event_registrants": lambda: _event_registrants(campaign.event),
        "ticket_type": lambda: _ticket_type(campaign),
        "checked_in": lambda: _checked_in(campaign.event),
        "not_checked_in": lambda: _not_checked_in(campaign.event),
        "all_members": lambda: _all_members(),
        "staff": lambda: _staff(),
        "selected_members": lambda: _selected_members(campaign),
        "manual": lambda: _manual_emails(campaign),
    }
    resolver = dispatch.get(campaign.audience_type)
    return resolver() if resolver else []


def _subscribers():
    members = (
        Member.objects.filter(email_subscribe=True)
        .prefetch_related("contact_emails")
        .order_by("first_name", "last_name")
    )
    return _members_to_recipients(members)


def _event_registrants(event):
    registrations = (
        EventRegistration.objects.filter(event=event)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return _registrations_to_recipients(registrations)


def _selected_members(campaign):
    members = campaign.selected_members.prefetch_related("contact_emails").order_by("first_name", "last_name")
    send_all = campaign.member_email_scope == "all"
    seen = set()
    recipients = []
    for member in members:
        if send_all:
            emails = [ce.email_address for ce in member.contact_emails.all() if ce.email_address]
        else:
            primary = member.get_primary_email()
            emails = [primary] if primary else []
        for email in emails:
            if email in seen:
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


def _manual_emails(campaign):
    recipients = []
    seen = set()
    for line in campaign.manual_emails.strip().splitlines():
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


def _ticket_type(campaign):
    """Registrants for a specific event + ticket type.

    The ticket UUID is stored in ``campaign.manual_emails``.
    """
    ticket_id = campaign.manual_emails.strip()
    if not ticket_id:
        return []
    registrations = (
        EventRegistration.objects.filter(event=campaign.event, ticket_id=ticket_id)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return _registrations_to_recipients(registrations)


def _checked_in(event):
    """Registrants who have at least one check-in record for the event."""
    from event.models import CheckInRecord

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

    checked_reg_ids = CheckInRecord.objects.filter(check_in__event=event).values_list("registration_id", flat=True)
    registrations = (
        EventRegistration.objects.filter(event=event)
        .exclude(pk__in=checked_reg_ids)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return _registrations_to_recipients(registrations)


def _all_members():
    """All active members with a primary email."""
    members = (
        Member.objects.filter(is_active=True).prefetch_related("contact_emails").order_by("first_name", "last_name")
    )
    return _members_to_recipients(members)


def _staff():
    """Staff members (is_staff=True) with a primary email."""
    members = (
        Member.objects.filter(is_staff=True, is_active=True)
        .prefetch_related("contact_emails")
        .order_by("first_name", "last_name")
    )
    return _members_to_recipients(members)


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


def _members_to_recipients(members):
    """Convert a Member queryset to deduplicated recipient dicts (primary email only)."""
    seen = set()
    recipients = []
    for member in members:
        email = member.get_primary_email()
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

"""Resolve campaign audience to a list of recipient dicts."""

from authn.models import Member
from event.models import EventRegistration


def get_recipients(campaign):
    """
    Return a deduplicated list of recipient dicts for the given campaign.

    Each dict contains: member_id, email, first_name, last_name, full_name.
    """
    if campaign.audience_type == "subscribers":
        return _subscribers()
    if campaign.audience_type == "event_registrants":
        return _event_registrants(campaign.event)
    if campaign.audience_type == "selected_members":
        return _selected_members(campaign)
    if campaign.audience_type == "manual":
        return _manual_emails(campaign)
    return []


def _subscribers():
    members = (
        Member.objects.filter(email_subscribe=True)
        .prefetch_related("contact_emails")
        .order_by("first_name", "last_name")
    )
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


def _event_registrants(event):
    registrations = (
        EventRegistration.objects.filter(event=event)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
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

from django.db.models import Exists, OuterRef
from django.db.models.functions import Lower

from apps.authn.models import ContactEmail, Member
from apps.event.models import EventRegistration

from .converters import (
    manual_emails_from_body,
    members_to_recipients,
    registrations_to_recipients,
)


def recipients_for_audience(
    audience_type: str,
    *,
    send_all: bool,
    event,
    ticket_uuid_str: str,
    selected_members,
    manual_emails_body: str,
):
    dispatch = {
        "subscribers": lambda: _subscribers(send_all),
        "event_registrants": lambda: _event_registrants(event),
        "ticket_type": lambda: _ticket_type_for_event(event, ticket_uuid_str),
        "checked_in": lambda: _checked_in(event),
        "not_checked_in": lambda: _not_checked_in(event),
        "all_members": lambda: _all_members(send_all),
        "staff": lambda: _staff(send_all),
        "selected_members": lambda: _selected_members_from(selected_members, send_all),
        "manual": lambda: _manual(manual_emails_body),
    }
    resolver = dispatch.get(audience_type)
    return resolver() if resolver else []


def _subscribers(send_all=False):
    """Active members, each at the addresses whose own ``subscribe`` flag is on.

    The per-address flag is authoritative: scope "primary" mails the primary only when it is subscribed, scope
    "all" mails every subscribed address. ``verified`` is not required (imported addresses start unverified).
    """
    subscribed = ContactEmail.objects.filter(member=OuterRef("pk"), subscribe=True)
    if not send_all:
        subscribed = subscribed.filter(email_type="primary")
    members = (
        Member.objects.filter(Exists(subscribed), is_active=True)
        .prefetch_related("contact_emails")
        .order_by("first_name", "last_name")
    )
    return members_to_recipients(members, send_all=send_all, subscribed_only=True)


def _event_registrants(event):
    if not event:
        return []
    registrations = (
        EventRegistration.objects.filter(event=event)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return registrations_to_recipients(registrations)


def _selected_members_from(selected_members, send_all):
    members = selected_members.prefetch_related("contact_emails").order_by(
        "first_name",
        "last_name",
    )
    return members_to_recipients(members, send_all=send_all)


def _ticket_type_for_event(event, ticket_id: str):
    if not event or not ticket_id:
        return []
    registrations = (
        EventRegistration.objects.filter(event=event, ticket_id=ticket_id)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return registrations_to_recipients(registrations)


def _checked_in(event):
    from apps.event.models import CheckInRecord

    if not event:
        return []
    checked_reg_ids = CheckInRecord.objects.filter(check_in__event=event).values_list("registration_id", flat=True)
    registrations = (
        EventRegistration.objects.filter(event=event, pk__in=checked_reg_ids)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return registrations_to_recipients(registrations)


def _not_checked_in(event):
    from apps.event.models import CheckInRecord

    if not event:
        return []
    checked_reg_ids = CheckInRecord.objects.filter(check_in__event=event).values_list("registration_id", flat=True)
    registrations = (
        EventRegistration.objects.filter(event=event)
        .exclude(pk__in=checked_reg_ids)
        .select_related("member")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return registrations_to_recipients(registrations)


def _manual(body):
    """The typed addresses, each attached to the active member it belongs to (matched case-insensitively).

    A matched recipient gets that member's name, personal ``{{login_link}}`` and unsubscribe link, as with Selected
    Members; the message still goes to the address exactly as typed, which is that member's own contact email.
    """
    recipients = manual_emails_from_body(body)
    members = _active_members_by_address([recipient["email"] for recipient in recipients])
    for recipient in recipients:
        member = members.get(recipient["email"].lower())
        if member is not None:
            recipient.update(
                member_id=member.id,
                first_name=member.first_name or "",
                last_name=member.last_name or "",
                full_name=member.get_full_name(),
            )
    return recipients


def _active_members_by_address(addresses):
    """``{lowercased address: member}`` for the addresses that belong to exactly one active member (one query).

    An address held by two members in different letter case (legacy rows) is ambiguous and matches neither.
    """
    if not addresses:
        return {}
    contacts = (
        ContactEmail.objects.annotate(address=Lower("email_address"))
        .filter(address__in={address.lower() for address in addresses}, member__is_active=True)
        .select_related("member")
    )
    owners = {}
    for contact in contacts:
        owners.setdefault(contact.address, {})[contact.member_id] = contact.member
    return {address: next(iter(found.values())) for address, found in owners.items() if len(found) == 1}


def _all_members(send_all=False):
    members = (
        Member.objects.filter(is_active=True).prefetch_related("contact_emails").order_by("first_name", "last_name")
    )
    return members_to_recipients(members, send_all=send_all)


def _staff(send_all=False):
    members = (
        Member.objects.filter(is_staff=True, is_active=True)
        .prefetch_related("contact_emails")
        .order_by("first_name", "last_name")
    )
    return members_to_recipients(members, send_all=send_all)

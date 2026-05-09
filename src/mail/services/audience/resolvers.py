from authn.models import Member
from event.models import EventRegistration

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
        "manual": lambda: manual_emails_from_body(manual_emails_body),
    }
    resolver = dispatch.get(audience_type)
    return resolver() if resolver else []


def _subscribers(send_all=False):
    members = (
        Member.objects.filter(
            contact_emails__subscribe=True,
            contact_emails__email_type="primary",
        )
        .distinct()
        .prefetch_related("contact_emails")
        .order_by("first_name", "last_name")
    )
    return members_to_recipients(members, send_all=send_all)


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
    from event.models import CheckInRecord

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
    return registrations_to_recipients(registrations)


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

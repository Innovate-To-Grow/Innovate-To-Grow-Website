"""Who a Broadcast SMS goes to: each audience's members or registrants, and manually entered numbers."""

from apps.authn.models import Member
from apps.event.models import EventRegistration
from apps.mail.models.sms_campaign import E164_RE, parse_manual_sms_phones

from ..policy.opt_outs import split_opted_out
from .phones import members_to_sms_recipients, registrations_to_sms_recipients


class SmsRecipients(list):
    """An SMS campaign's recipients, with ``skipped``: the rows left out because their number is on the SMS opt-out
    list (it replied STOP, or staff opted it out)."""

    def __init__(self, recipients=(), skipped=()):
        super().__init__(recipients)
        self.skipped = list(skipped)


def get_sms_recipients(campaign):
    return SmsRecipients(*split_opted_out(_audience_recipients(campaign)))


def _audience_recipients(campaign):
    recipients = recipients_for_sms_audience(
        campaign.audience_type,
        phone_policy=campaign.phone_policy,
        event=campaign.event,
        ticket_uuid_str=campaign.ticket_id.strip() if campaign.audience_type == "ticket_type" else "",
        selected_members=campaign.selected_members,
        manual_phones_body=campaign.manual_phones if campaign.audience_type == "manual" else "",
    )

    exclude_type = (campaign.exclude_audience_type or "").strip()
    if not exclude_type:
        return recipients

    excluded = recipients_for_sms_audience(
        exclude_type,
        phone_policy=campaign.phone_policy,
        event=campaign.exclude_event,
        ticket_uuid_str=campaign.exclude_ticket_id.strip() if exclude_type == "ticket_type" else "",
        selected_members=campaign.exclude_members,
        manual_phones_body="",
    )
    excluded_phones = {recipient["phone"] for recipient in excluded if recipient.get("phone")}
    return [recipient for recipient in recipients if recipient.get("phone") not in excluded_phones]


def recipients_for_sms_audience(
    audience_type: str,
    *,
    phone_policy: str,
    event,
    ticket_uuid_str: str,
    selected_members,
    manual_phones_body: str,
):
    dispatch = {
        "subscribers": lambda: _subscribers(phone_policy),
        "event_registrants": lambda: _event_registrants(event, phone_policy),
        "ticket_type": lambda: _ticket_type_for_event(event, ticket_uuid_str, phone_policy),
        "checked_in": lambda: _checked_in(event, phone_policy),
        "not_checked_in": lambda: _not_checked_in(event, phone_policy),
        "all_members": lambda: _all_members(phone_policy),
        "staff": lambda: _staff(phone_policy),
        "selected_members": lambda: _selected_members_from(selected_members, phone_policy),
        "manual": lambda: manual_sms_recipients_from_body(manual_phones_body),
    }
    resolver = dispatch.get(audience_type)
    return resolver() if resolver else []


def manual_sms_recipients_from_body(body: str):
    recipients = []
    for phone in parse_manual_sms_phones(body):
        if not E164_RE.match(phone):
            continue
        recipients.append(
            {
                "member_id": None,
                "phone": phone,
                "first_name": "",
                "last_name": "",
                "full_name": "",
            }
        )
    return recipients


def _subscribers(phone_policy):
    members = (
        Member.objects.filter(contact_phones__subscribe=True, contact_phones__verified=True)
        .distinct()
        .prefetch_related("contact_phones")
        .order_by("first_name", "last_name")
    )
    return members_to_sms_recipients(members, phone_policy=phone_policy)


def _all_members(phone_policy):
    members = (
        Member.objects.filter(is_active=True).prefetch_related("contact_phones").order_by("first_name", "last_name")
    )
    return members_to_sms_recipients(members, phone_policy=phone_policy)


def _staff(phone_policy):
    members = (
        Member.objects.filter(is_staff=True, is_active=True)
        .prefetch_related("contact_phones")
        .order_by("first_name", "last_name")
    )
    return members_to_sms_recipients(members, phone_policy=phone_policy)


def _selected_members_from(selected_members, phone_policy):
    members = selected_members.prefetch_related("contact_phones").order_by("first_name", "last_name")
    return members_to_sms_recipients(members, phone_policy=phone_policy)


def _event_registrants(event, phone_policy):
    if not event:
        return []
    registrations = (
        EventRegistration.objects.filter(event=event)
        .select_related("member")
        .prefetch_related("member__contact_phones")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return registrations_to_sms_recipients(registrations, phone_policy=phone_policy)


def _ticket_type_for_event(event, ticket_id: str, phone_policy):
    if not event or not ticket_id:
        return []
    registrations = (
        EventRegistration.objects.filter(event=event, ticket_id=ticket_id)
        .select_related("member")
        .prefetch_related("member__contact_phones")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return registrations_to_sms_recipients(registrations, phone_policy=phone_policy)


def _checked_in(event, phone_policy):
    from apps.event.models import CheckInRecord

    if not event:
        return []
    checked_reg_ids = CheckInRecord.objects.filter(check_in__event=event).values_list("registration_id", flat=True)
    registrations = (
        EventRegistration.objects.filter(event=event, pk__in=checked_reg_ids)
        .select_related("member")
        .prefetch_related("member__contact_phones")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return registrations_to_sms_recipients(registrations, phone_policy=phone_policy)


def _not_checked_in(event, phone_policy):
    from apps.event.models import CheckInRecord

    if not event:
        return []
    checked_reg_ids = CheckInRecord.objects.filter(check_in__event=event).values_list("registration_id", flat=True)
    registrations = (
        EventRegistration.objects.filter(event=event)
        .exclude(pk__in=checked_reg_ids)
        .select_related("member")
        .prefetch_related("member__contact_phones")
        .order_by("attendee_first_name", "attendee_last_name")
    )
    return registrations_to_sms_recipients(registrations, phone_policy=phone_policy)

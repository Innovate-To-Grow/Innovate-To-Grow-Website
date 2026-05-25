from authn.models import ContactPhone, Member
from event.models import EventRegistration
from mail.models.sms_campaign import E164_RE, parse_manual_sms_phones


def get_sms_recipients(campaign):
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
    from event.models import CheckInRecord

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
    from event.models import CheckInRecord

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


def members_to_sms_recipients(members, *, phone_policy: str):
    recipients = []
    seen = set()
    for member in members:
        contact_phone = _first_eligible_member_phone(member, phone_policy)
        if contact_phone is None:
            continue
        phone = contact_phone.to_e164()
        if phone in seen:
            continue
        seen.add(phone)
        recipients.append(_member_recipient(member, phone))
    return recipients


def registrations_to_sms_recipients(registrations, *, phone_policy: str):
    recipients = []
    seen = set()
    for registration in registrations:
        phone = _phone_for_registration(registration, phone_policy)
        if not phone or phone in seen:
            continue
        seen.add(phone)
        first = registration.attendee_first_name or registration.member.first_name or ""
        last = registration.attendee_last_name or registration.member.last_name or ""
        recipients.append(
            {
                "member_id": registration.member_id,
                "phone": phone,
                "first_name": first,
                "last_name": last,
                "full_name": f"{first} {last}".strip(),
            }
        )
    return recipients


def _phone_for_registration(registration, phone_policy: str) -> str:
    contact_phone = _first_eligible_member_phone(registration.member, phone_policy)
    if contact_phone is not None:
        return contact_phone.to_e164()
    if (
        phone_policy == "any_verified"
        and registration.phone_verified
        and E164_RE.match(registration.attendee_phone or "")
    ):
        return registration.attendee_phone
    return ""


def _first_eligible_member_phone(member, phone_policy: str):
    phones = getattr(member, "_prefetched_objects_cache", {}).get("contact_phones")
    if phones is None:
        phones = member.contact_phones.all()
    eligible = [phone for phone in phones if _contact_phone_is_eligible(phone, phone_policy)]
    eligible.sort(key=lambda phone: (not phone.subscribe, phone.created_at))
    return eligible[0] if eligible else None


def _contact_phone_is_eligible(contact_phone: ContactPhone, phone_policy: str) -> bool:
    if not contact_phone.verified:
        return False
    if phone_policy == "verified_opt_in":
        return contact_phone.subscribe
    return True


def _member_recipient(member, phone: str):
    return {
        "member_id": member.id,
        "phone": phone,
        "first_name": member.first_name or "",
        "last_name": member.last_name or "",
        "full_name": member.get_full_name(),
    }

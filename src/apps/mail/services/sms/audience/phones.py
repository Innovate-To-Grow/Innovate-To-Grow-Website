"""Which number a member or a registrant is texted at, and the recipient row built for them."""

from apps.authn.models import ContactPhone
from apps.mail.models.sms.campaign import E164_RE


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

"""The SMS opt-out list (``SmsOptOut``): the lookups every send path and audience make, and the changes to it.

Numbers compare in E.164 (``+12095551234``); the site texts US numbers only. ``register()`` (``MailConfig.ready()``)
installs the list in core's send check, so every SMS the site sends asks ``is_opted_out`` first, and AWS refusing a
number as opted out lands here as a ``send_refusal`` row before the next sync.

An active opt-out also sets the members' matching contact phones to not subscribed, once. Nothing here ever
subscribes a phone again: a person who replies START is texted again only after choosing to subscribe.
"""

import re

from django.db import transaction
from django.utils import timezone

from apps.authn.models import ContactPhone
from apps.mail.models import SmsOptOut
from apps.mail.models.sms_campaign import E164_RE

US_COUNTRY_CODE = "1"
US_REGION = "1-US"
SKIPPED_MESSAGE = "Not sent: this number opted out of texts (Mail → SMS Opt-outs)."


def normalize_phone(value) -> str:
    """The E.164 form of ``value`` (US national digits get +1), or "" when it is not a number the site can text."""
    text = re.sub(r"[\s().-]", "", str(value or "").strip())
    if not text:
        return ""
    if not text.startswith("+"):
        digits = re.sub(r"\D", "", text)
        if len(digits) == 10:
            text = f"+{US_COUNTRY_CODE}{digits}"
        elif len(digits) == 11 and digits.startswith(US_COUNTRY_CODE):
            text = f"+{digits}"
        else:
            return ""
    return text if E164_RE.match(text) else ""


def us_national_digits(e164: str) -> str:
    """The ``ContactPhone.phone_number`` of a US E.164 number, or "" for any other number."""
    if e164.startswith(f"+{US_COUNTRY_CODE}") and len(e164) == 12:
        return e164[2:]
    return ""


def active_opt_outs():
    return SmsOptOut.objects.filter(cleared_at__isnull=True)


def is_opted_out(phone) -> bool:
    number = normalize_phone(phone)
    return bool(number) and active_opt_outs().filter(phone_number=number).exists()


def opted_out_numbers(numbers) -> frozenset[str]:
    """Which of ``numbers`` (E.164) are on the list, in one query."""
    wanted = {number for number in numbers if number}
    if not wanted:
        return frozenset()
    return frozenset(active_opt_outs().filter(phone_number__in=wanted).values_list("phone_number", flat=True))


def split_opted_out(recipients, *, key: str = "phone") -> tuple[list, list]:
    """``(kept, skipped)``: the audience rows whose number may be texted, and those on the opt-out list."""
    blocked = opted_out_numbers(normalize_phone(recipient.get(key)) for recipient in recipients)
    if not blocked:
        return list(recipients), []
    kept, skipped = [], []
    for recipient in recipients:
        (skipped if normalize_phone(recipient.get(key)) in blocked else kept).append(recipient)
    return kept, skipped


def record_refusal(phone) -> None:
    """AWS refused a send to ``phone`` because it opted out: put it on the list now (the sync confirms it later)."""
    number = normalize_phone(phone)
    if not number:
        return
    row = open_opt_out(number, source=SmsOptOut.Source.SEND_REFUSAL, opted_out_at=timezone.now())
    unsubscribe_contact_phones(row)


def open_opt_out(number: str, *, source: str, opted_out_at, **fields) -> SmsOptOut:
    """The active row for ``number``: created, reopened when it had opted back in, or the existing active one."""
    with transaction.atomic():
        row = SmsOptOut.objects.select_for_update().filter(phone_number=number).first()
        if row is None:
            return SmsOptOut.objects.create(phone_number=number, source=source, opted_out_at=opted_out_at, **fields)
        if row.cleared_at is None:
            return row
        values = {
            "source": source,
            "opted_out_at": opted_out_at,
            "cleared_at": None,
            "cleared_reason": "",
            "contacts_unsubscribed_at": None,
            **fields,
        }
        for name, value in values.items():
            setattr(row, name, value)
        row.save(update_fields=[*values, "updated_at"])
        return row


def unsubscribe_contact_phones(row: SmsOptOut) -> int:
    """Set the members' phones with this number to not subscribed, once per opt-out; how many were changed."""
    if row.cleared_at is not None or row.contacts_unsubscribed_at is not None:
        return 0
    now = timezone.now()
    with transaction.atomic():
        claimed = SmsOptOut.objects.filter(
            pk=row.pk, cleared_at__isnull=True, contacts_unsubscribed_at__isnull=True
        ).update(contacts_unsubscribed_at=now, updated_at=now)
        if not claimed:
            return 0
        national = us_national_digits(row.phone_number)
        changed = 0
        if national:
            changed = ContactPhone.objects.filter(phone_number=national, region=US_REGION, subscribe=True).update(
                subscribe=False, updated_at=now
            )
    row.contacts_unsubscribed_at = now
    return changed


def add_staff_opt_out(phone, *, note: str, actor) -> SmsOptOut:
    """Staff opt a number out (a person asked them to stop texting it)."""
    number = normalize_phone(phone)
    if not number:
        raise ValueError("Enter a US phone number in E.164 form, for example +12095551234.")
    row = open_opt_out(
        number, source=SmsOptOut.Source.STAFF, opted_out_at=timezone.now(), note=note[:500], created_by=actor
    )
    unsubscribe_contact_phones(row)
    return row


def lift_staff_opt_out(row: SmsOptOut, *, actor) -> bool:
    """Staff lift a staff opt-out; AWS opt-outs are lifted only by AWS (the person replies START)."""
    if row.source != SmsOptOut.Source.STAFF or row.cleared_at is not None:
        return False
    actor_label = getattr(actor, "email", "") or "staff"
    return bool(
        SmsOptOut.objects.filter(pk=row.pk, source=SmsOptOut.Source.STAFF, cleared_at__isnull=True).update(
            cleared_at=timezone.now(), cleared_reason=f"Lifted by {actor_label}"[:200], updated_at=timezone.now()
        )
    )


def matching_contact_phones(numbers) -> dict[str, list[ContactPhone]]:
    """The contact phones (with their members) of each E.164 number, for the admin's list."""
    by_national = {us_national_digits(number): number for number in numbers if us_national_digits(number)}
    matches: dict[str, list[ContactPhone]] = {}
    phones = ContactPhone.objects.filter(phone_number__in=list(by_national), region=US_REGION).select_related("member")
    for phone in phones:
        matches.setdefault(by_national[phone.phone_number], []).append(phone)
    return matches


def register() -> None:
    from apps.core.services.aws.sms_opt_outs import register_opt_out_list

    register_opt_out_list(is_opted_out=is_opted_out, record_refusal=record_refusal)

"""Copy a campaign into a new editable draft: its message and audience, nothing of its send."""

import re

from apps.mail.models import BouncedAddress, EmailCampaign, RecipientLog
from apps.mail.services.audience.suppression import normalize_address

# What a copy keeps. Status, the counters, sent_at, sent_by and error_message start over; recipient logs and
# login links belong to the send that created them and are never copied.
COPIED_FIELDS = (
    "subject",
    "body",
    "login_redirect_path",
    "login_link_validity_days",
    "login_link_reusable",
    "include_unsubscribe_header",
    "audience_type",
    "event_id",
    "member_email_scope",
    "manual_emails",
    "exclude_audience_type",
    "exclude_member_email_scope",
    "exclude_event_id",
    "exclude_ticket_id",
)
# An empty Manual Emails audience with no exclusions, for sending the same email to further addresses.
NEW_MANUAL_AUDIENCE = {
    "audience_type": "manual",
    "event_id": None,
    "manual_emails": "",
    "exclude_audience_type": "",
    "exclude_member_email_scope": "primary",
    "exclude_event_id": None,
    "exclude_ticket_id": "",
}
NAME_MAX_LENGTH = EmailCampaign._meta.get_field("name").max_length
UNTITLED = "Untitled"
# A copy is named like a file system names one: "<base> (1)", "<base> (2)", with the lowest number no campaign uses.
# The base is the original's name without what earlier copies added: any run of leading "Copy of" (the former
# naming, in any letter case) and one trailing " (N)". "Copy office hours" keeps its words.
_COPY_PREFIX_RE = re.compile(r"^(?:copy\s+of\b\s*)+", re.IGNORECASE)
_NUMBER_SUFFIX_RE = re.compile(r"\s*\(\d+\)$")
# Room kept for the suffix when the base is cut to the name field: " (9999)".
_SUFFIX_RESERVE = 7


def retry_address_for(campaign, raw):
    """One eligible address this campaign actually mailed, or empty when a retry draft must not be offered."""
    address = normalize_address(raw)
    if (
        not address
        or len(address) > 254
        or not RecipientLog.objects.filter(
            campaign=campaign, email_address__iexact=address, sent_at__isnull=False
        ).exists()
    ):
        return ""
    row = BouncedAddress.objects.filter(address=address).first()
    if (
        row is None
        or row.is_suppressed
        or row.complaint_count
        or row.ses_permanent_count
        or row.category_count("hard")
        or row.category_count("mailbox_disabled")
    ):
        return ""
    return address


def base_name(name: str) -> str:
    """*name* without leading ``Copy of`` prefixes and a trailing ``(N)``, or ``Untitled`` when nothing is left."""
    stripped = _NUMBER_SUFFIX_RE.sub("", _COPY_PREFIX_RE.sub("", (name or "").strip())).strip()
    return stripped or UNTITLED


def copy_name(name: str) -> str:
    """``<base> (N)`` with the lowest N that no existing campaign name carries (compared ignoring letter case).

    Querying the names that start with the base is one query however many copies exist. A long base is cut so the
    suffix fits the name field.
    """
    base = base_name(name)[: NAME_MAX_LENGTH - _SUFFIX_RESERVE]
    taken = {
        existing.lower()
        for existing in EmailCampaign.objects.filter(name__istartswith=base).values_list("name", flat=True)
    }
    number = 1
    while f"{base} ({number})".lower() in taken:
        number += 1
    return f"{base} ({number})"


def duplicate_campaign(campaign, *, name: str = "", new_manual_audience: bool = False) -> EmailCampaign:
    """A new draft with *campaign*'s subject, body, settings and audience.

    With ``new_manual_audience`` the draft starts with an empty Manual Emails list instead (and no exclusions):
    the way to send the same email to more people, since a campaign that has been sent is locked.
    """
    values = {field: getattr(campaign, field) for field in COPIED_FIELDS}
    if new_manual_audience:
        values.update(NEW_MANUAL_AUDIENCE)
    copy = EmailCampaign.objects.create(name=(name.strip() or copy_name(campaign.name))[:NAME_MAX_LENGTH], **values)
    if not new_manual_audience:
        copy.selected_members.set(campaign.selected_members.all())
        copy.exclude_members.set(campaign.exclude_members.all())
    return copy

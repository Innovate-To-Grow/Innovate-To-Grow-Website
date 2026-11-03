"""Copy a campaign into a new editable draft: its message and audience, nothing of its send."""

from apps.mail.models import EmailCampaign

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
COPY_NAME_PREFIX = "Copy of "
NAME_MAX_LENGTH = EmailCampaign._meta.get_field("name").max_length


def copy_name(name: str) -> str:
    """``Copy of <name>``, cut to the length of the name field."""
    return (COPY_NAME_PREFIX + (name or "Untitled"))[:NAME_MAX_LENGTH]


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

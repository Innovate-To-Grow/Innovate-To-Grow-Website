"""Resolve campaign audience to a list of recipient dicts."""

from .resolvers import recipients_for_audience


def get_recipients(campaign):
    send_all = campaign.member_email_scope == "all"
    recipients = recipients_for_audience(
        campaign.audience_type,
        send_all=send_all,
        event=campaign.event,
        ticket_uuid_str=(campaign.manual_emails.strip() if campaign.audience_type == "ticket_type" else ""),
        selected_members=campaign.selected_members,
        manual_emails_body=(campaign.manual_emails if campaign.audience_type == "manual" else ""),
    )

    exclude_type = (campaign.exclude_audience_type or "").strip()
    if not exclude_type:
        return recipients

    excluded = recipients_for_audience(
        exclude_type,
        send_all=campaign.exclude_member_email_scope == "all",
        event=campaign.exclude_event,
        ticket_uuid_str=(campaign.exclude_ticket_id.strip() if exclude_type == "ticket_type" else ""),
        selected_members=campaign.exclude_members,
        manual_emails_body="",
    )
    exclude_emails = {recipient["email"].lower() for recipient in excluded if recipient.get("email")}
    return [
        recipient
        for recipient in recipients
        if recipient.get("email") and recipient["email"].lower() not in exclude_emails
    ]


__all__ = ["get_recipients"]

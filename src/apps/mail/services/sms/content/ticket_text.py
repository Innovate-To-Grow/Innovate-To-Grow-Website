"""What a ticket text says, and the link it carries."""

from apps.mail.models import SmsConfig

from ...campaign.content.personalize import personalize
from ..links import Purpose, issue_personal_link, issue_redirect_link, may_text_personal_link, sign_in_path
from .compose import apply_footer


def ticket_text(registration, link: str, config: SmsConfig) -> str:
    values = {
        "first_name": registration.attendee_first_name or registration.member.first_name or "",
        "event_name": registration.event.name,
        "ticket_link": link,
    }
    return apply_footer(personalize(config.ticket_sms_template, values), config)


def _ticket_link(registration, config: SmsConfig, phone: str) -> str:
    """A personal link when personal links are on and ``phone`` is the registrant's own verified account phone (a
    phone verified only for this registration may be someone else's), else one that opens the sign-in page."""
    from apps.event.services.ticket.mail import ticket_login_redirect_path

    destination = ticket_login_redirect_path(registration)
    days = config.ticket_link_validity_days
    if config.personal_links_enabled and may_text_personal_link(registration.member, phone):
        url = issue_personal_link(
            purpose=Purpose.TICKET,
            member=registration.member,
            phone=phone,
            redirect_path=destination,
            validity_days=days,
            registration=registration,
        )
        if url is not None:  # None: personal sign-in links were turned off meanwhile.
            return url
    return issue_redirect_link(
        purpose=Purpose.TICKET, redirect_path=sign_in_path(destination), validity_days=days, registration=registration
    )

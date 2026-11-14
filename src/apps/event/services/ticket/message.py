"""What the ticket email says: its MIME message (HTML body, inline barcode, calendar invite) and the one-tap sign-in
link it carries."""

from urllib.parse import quote

from django.db import transaction
from django.template.loader import render_to_string

from apps.core.services.email import (
    EmailAttachment,
    EmailMessage,
)
from apps.event.models import EventRegistration
from apps.event.services.ticket.assets import generate_ticket_barcode_png_bytes
from apps.event.services.ticket.calendar import build_google_calendar_url, generate_ics
from apps.event.services.ticket.date_ranges import format_event_date_range


def _build_mime_message(*, subject, from_address, recipients, html_body, barcode_bytes, ics_data):
    """Build the provider-neutral ticket message with PDF417 and ICS attachments.

    The ticket code and the member's login link are credentials, so the message leaves no Sent Items copy.
    """
    del from_address  # The active provider owns the configured sender address.
    return EmailMessage(
        subject=subject,
        to=tuple(recipients),
        html_body=html_body,
        keep_sent_copy=False,
        attachments=(
            EmailAttachment(
                "ticket-barcode.png",
                barcode_bytes,
                "image/png",
                disposition="inline",
                content_id="ticket-barcode",
            ),
            EmailAttachment("event.ics", ics_data.encode("utf-8"), "text/calendar"),
        ),
    )


TICKET_LOGIN_REDIRECT_PATH = "/event-registration"


def ticket_login_redirect_path(registration: EventRegistration) -> str:
    return f"{TICKET_LOGIN_REDIRECT_PATH}?event={quote(registration.event.slug)}"


def _issue_ticket_login_link(registration: EventRegistration) -> str:
    """Issue a unified login link for a ticket email, replacing any earlier one.

    Resending a ticket email revokes the previous link so only the most recent
    email's link works — same semantics as the old per-registration token slot.
    """
    from apps.mail.services.tokens.login_links import create_login_link, revoke_login_links

    if not registration.member_id:
        return ""

    with transaction.atomic():
        revoke_login_links(registration.login_tokens.all())
        url, _login_link = create_login_link(
            member_id=registration.member_id,
            registration=registration,
            redirect_path=ticket_login_redirect_path(registration),
            validity_days=registration.event.ticket_login_validity_days,
        )
    return url


def _prepare_ticket_login_link(registration: EventRegistration):
    """Issue a provisional link without invalidating the last delivered link."""
    from apps.mail.services.tokens.login_links import create_login_link

    if not registration.member_id:
        return "", None

    return create_login_link(
        member_id=registration.member_id,
        registration=registration,
        redirect_path=ticket_login_redirect_path(registration),
        validity_days=registration.event.ticket_login_validity_days,
    )


def _build_ticket_message(registration: EventRegistration, *, config, login_url: str):
    """The ticket email: confirmation body, inline barcode and calendar invite, to both attendee addresses."""
    event = registration.event
    google_cal_url = build_google_calendar_url(
        event_name=event.name,
        event_start_date=event.date,
        event_end_date=event.effective_end_date,
        event_location=event.location,
        event_description=event.description,
    )
    html_body = render_to_string(
        "event/email/ticket_confirmation.html",
        {
            "attendee_name": registration.attendee_name or registration.attendee_email,
            "event_name": event.name,
            "event_date_range": format_event_date_range(event.date, event.effective_end_date),
            "event_location": event.location,
            "ticket_name": registration.ticket.name,
            "ticket_code": registration.ticket_code,
            "event_description": event.description,
            "login_url": login_url,
            "google_calendar_url": google_cal_url,
        },
    )

    barcode_bytes = generate_ticket_barcode_png_bytes(registration)
    ics_data = generate_ics(
        event_uid=str(event.pk),
        event_name=event.name,
        event_start_date=event.date,
        event_end_date=event.effective_end_date,
        event_location=event.location,
        event_description=event.description,
    )

    recipients = [registration.attendee_email]
    if registration.attendee_secondary_email:
        recipients.append(registration.attendee_secondary_email)

    subject = f"Your Ticket: {event.name} - Innovate to Grow"
    return _build_mime_message(
        subject=subject,
        from_address=config.source_address,
        recipients=recipients,
        html_body=html_body,
        barcode_bytes=barcode_bytes,
        ics_data=ics_data,
    )

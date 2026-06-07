"""
Ticket confirmation email service.

Sends a branded HTML email with an inline PDF417 barcode image.
Uses AWS SES through the shared Notification Delivery configuration.
"""

import logging
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials
from apps.event.models import EventRegistration
from apps.event.services.calendar import build_google_calendar_url, generate_ics
from apps.event.services.ticket_assets import (
    generate_ticket_barcode_png_bytes,
)

logger = logging.getLogger(__name__)


def _load_config():
    from apps.core.models import EmailServiceConfig

    return EmailServiceConfig.load()


def _build_mime_message(*, subject, from_address, recipients, html_body, barcode_bytes, ics_data):
    """Build a multipart/mixed MIME message with an inline barcode and .ics attachment."""
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = ", ".join(recipients)

    # Inline content (HTML + barcode image)
    related = MIMEMultipart("related")
    related.attach(MIMEText(html_body, "html", "utf-8"))

    barcode_image = MIMEImage(barcode_bytes, "png")
    barcode_image.add_header("Content-ID", "<ticket-barcode>")
    barcode_image.add_header("Content-Disposition", "inline", filename="ticket-barcode.png")
    related.attach(barcode_image)

    msg.attach(related)

    # .ics calendar attachment
    ics_attachment = MIMEText(ics_data, "calendar", "utf-8")
    ics_attachment.add_header("Content-Disposition", "attachment", filename="event.ics")
    msg.attach(ics_attachment)

    return msg


def _send_via_ses(*, config, mime_message) -> bool:
    """Attempt to send via AWS SES send_raw_email. Returns True on success."""
    if not config.ses_configured:
        return False
    try:
        creds = resolve_aws_credentials("ses")
        client = boto3.client(
            "ses",
            region_name=creds.region,
            aws_access_key_id=creds.access_key_id,
            aws_secret_access_key=creds.secret_access_key,
        )
        client.send_raw_email(RawMessage={"Data": mime_message.as_string()})
        return True
    except AwsCredentialsError:
        logger.warning("SES send skipped: AWS credentials are not configured")
        return False
    except (BotoCoreError, ClientError):
        logger.exception("SES send_raw_email failed")
        return False


TICKET_LOGIN_REDIRECT_PATH = "/event-registration"


def _issue_ticket_login_link(registration: EventRegistration) -> str:
    """Issue a unified login link for a ticket email, replacing any earlier one.

    Resending a ticket email revokes the previous link so only the most recent
    email's link works — same semantics as the old per-registration token slot.
    """
    from apps.mail.services.login_links import issue_login_link, revoke_login_links

    if not registration.member_id:
        return ""

    revoke_login_links(registration.login_tokens.all())
    return issue_login_link(
        member_id=registration.member_id,
        registration=registration,
        redirect_path=TICKET_LOGIN_REDIRECT_PATH,
        validity_days=registration.event.ticket_login_validity_days,
    )


def send_ticket_email(registration: EventRegistration) -> None:
    """
    Send a ticket confirmation email with an inline barcode.

    Updates registration.ticket_email_sent_at on success or
    registration.ticket_email_error on failure.
    """
    config = _load_config()

    login_url = _issue_ticket_login_link(registration)

    event = registration.event
    google_cal_url = build_google_calendar_url(
        event_name=event.name,
        event_date=event.date,
        event_location=event.location,
        event_description=event.description,
    )
    html_body = render_to_string(
        "event/email/ticket_confirmation.html",
        {
            "attendee_name": registration.attendee_name or registration.attendee_email,
            "event_name": event.name,
            "event_date": event.date.strftime("%B %d, %Y"),
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
        event_date=event.date,
        event_location=event.location,
        event_description=event.description,
    )

    recipients = [registration.attendee_email]
    if registration.attendee_secondary_email:
        recipients.append(registration.attendee_secondary_email)

    subject = f"Your Ticket: {event.name} - Innovate to Grow"

    mime_message = _build_mime_message(
        subject=subject,
        from_address=config.source_address,
        recipients=recipients,
        html_body=html_body,
        barcode_bytes=barcode_bytes,
        ics_data=ics_data,
    )

    try:
        if _send_via_ses(config=config, mime_message=mime_message):
            logger.info("Ticket email sent via SES for registration %s", registration.pk)
        else:
            raise RuntimeError("Ticket email delivery via AWS SES failed or is not configured.")

        registration.ticket_email_sent_at = timezone.now()
        registration.ticket_email_error = ""
        registration.save(update_fields=["ticket_email_sent_at", "ticket_email_error"])
    except Exception as exc:
        logger.exception("Failed to send ticket email for registration %s", registration.pk)
        registration.ticket_email_error = str(exc)
        registration.save(update_fields=["ticket_email_error"])
        raise

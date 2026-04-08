"""
Ticket confirmation email service.

Sends a branded HTML email with an inline PDF417 barcode image.
Uses AWS SES (primary) with Django SMTP fallback — same dual-provider
pattern as authn.services.email.send_email.
"""

import logging
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.template.loader import render_to_string
from django.utils import timezone

from event.models import EventRegistration
from event.services.calendar import build_google_calendar_url, generate_ics
from event.services.ticket_assets import (
    build_frontend_absolute_url,
    build_ticket_login_token,
    generate_ticket_barcode_png_bytes,
)

logger = logging.getLogger(__name__)


def _load_config():
    from core.models import EmailServiceConfig

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
        client = boto3.client(
            "ses",
            region_name=config.ses_region,
            aws_access_key_id=config.ses_access_key_id,
            aws_secret_access_key=config.ses_secret_access_key,
        )
        client.send_raw_email(RawMessage={"Data": mime_message.as_string()})
        return True
    except (BotoCoreError, ClientError):
        logger.exception("SES send_raw_email failed")
        return False


def _send_via_smtp(*, config, mime_message):
    """Send via SMTP using DB-stored credentials."""
    from django.core.mail import get_connection

    connection = get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.smtp_username,
        password=config.smtp_password,
        use_tls=config.smtp_use_tls,
        fail_silently=False,
    )
    from django.core.mail import EmailMessage

    email = EmailMessage(
        subject=mime_message["Subject"],
        body=mime_message.as_string(),
        from_email=mime_message["From"],
        to=mime_message["To"].split(", "),
        connection=connection,
    )
    email.content_subtype = "html"
    # Replace the body with the full MIME message for inline images
    email.encoding = "utf-8"
    email.extra_headers = {"Content-Type": f'multipart/related; boundary="{mime_message.get_boundary()}"'}
    # Use the low-level connection to send the raw MIME message directly
    connection.open()
    try:
        connection.connection.sendmail(
            mime_message["From"],
            mime_message["To"].split(", "),
            mime_message.as_string(),
        )
    finally:
        connection.close()


def send_ticket_email(registration: EventRegistration) -> None:
    """
    Send a ticket confirmation email with an inline barcode.

    Updates registration.ticket_email_sent_at on success or
    registration.ticket_email_error on failure.
    """
    config = _load_config()

    login_token = build_ticket_login_token(registration.member)
    login_url = build_frontend_absolute_url(f"/ticket-login?token={login_token}")

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
            logger.info("SES unavailable; falling back to SMTP for registration %s", registration.pk)
            _send_via_smtp(config=config, mime_message=mime_message)
            logger.info("Ticket email sent via SMTP for registration %s", registration.pk)

        registration.ticket_email_sent_at = timezone.now()
        registration.ticket_email_error = ""
        registration.save(update_fields=["ticket_email_sent_at", "ticket_email_error"])
    except Exception as exc:
        logger.exception("Failed to send ticket email for registration %s", registration.pk)
        registration.ticket_email_error = str(exc)
        registration.save(update_fields=["ticket_email_error"])
        raise

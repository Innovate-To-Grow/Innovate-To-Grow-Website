"""
Ticket confirmation email service.

Sends a branded HTML email with an inline PDF417 barcode image.
Uses AWS SES through the shared Notification Delivery configuration.
"""

import logging
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials
from apps.core.services.aws.provider_outcomes import (
    NO_PROVIDER_RETRIES,
    ProviderDeliveryError,
    classify_aws_send_failure,
)
from apps.event.models import EventRegistration
from apps.event.services.date_ranges import format_event_date_range
from apps.event.services.ticket.assets import generate_ticket_barcode_png_bytes
from apps.event.services.ticket.calendar import build_google_calendar_url, generate_ics

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


def _send_via_ses(
    *,
    config,
    mime_message,
    before_provider_call=None,
    raise_provider_errors: bool = False,
) -> bool:
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
            config=NO_PROVIDER_RETRIES,
        )
        if before_provider_call is not None:
            before_provider_call()
        client.send_raw_email(RawMessage={"Data": mime_message.as_string()})
        return True
    except AwsCredentialsError:
        logger.warning("SES send skipped: AWS credentials are not configured")
        return False
    except (BotoCoreError, ClientError) as exc:
        logger.exception("SES send_raw_email failed")
        if raise_provider_errors:
            outcome, message = classify_aws_send_failure(exc, provider="SES")
            raise ProviderDeliveryError(message, outcome=outcome) from exc
        return False


TICKET_LOGIN_REDIRECT_PATH = "/event-registration"


def ticket_login_redirect_path(registration: EventRegistration) -> str:
    return f"{TICKET_LOGIN_REDIRECT_PATH}?event={quote(registration.event.slug)}"


def _issue_ticket_login_link(registration: EventRegistration) -> str:
    """Issue a unified login link for a ticket email, replacing any earlier one.

    Resending a ticket email revokes the previous link so only the most recent
    email's link works — same semantics as the old per-registration token slot.
    """
    from apps.mail.services.login_links import create_login_link, revoke_login_links

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
    from apps.mail.services.login_links import create_login_link

    if not registration.member_id:
        return "", None

    return create_login_link(
        member_id=registration.member_id,
        registration=registration,
        redirect_path=ticket_login_redirect_path(registration),
        validity_days=registration.event.ticket_login_validity_days,
    )


def send_ticket_email(
    registration: EventRegistration,
    *,
    before_token_mutation=None,
    before_provider_call=None,
    raise_provider_errors: bool = False,
) -> None:
    """
    Send a ticket confirmation email with an inline barcode.

    Updates registration.ticket_email_sent_at on success or
    registration.ticket_email_error on failure.
    """
    issued_login_link = None
    provider_accepted = False
    provider_boundary_entered = False
    try:
        config = _load_config()
        if not config.ses_configured:
            raise RuntimeError("Ticket email delivery via AWS SES failed or is not configured.")

        # The callback locks and verifies a durable-job claim. Keeping it in the
        # same transaction as token creation prevents recovery from replacing
        # the claim between the fence and this side effect.
        with transaction.atomic():
            if before_token_mutation is not None:
                before_token_mutation()
            login_url, issued_login_link = _prepare_ticket_login_link(registration)

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
        mime_message = _build_mime_message(
            subject=subject,
            from_address=config.source_address,
            recipients=recipients,
            html_body=html_body,
            barcode_bytes=barcode_bytes,
            ics_data=ics_data,
        )

        def enter_provider_boundary():
            nonlocal provider_boundary_entered
            if before_provider_call is not None:
                before_provider_call()
            provider_boundary_entered = True

        send_kwargs = {
            "config": config,
            "mime_message": mime_message,
            "before_provider_call": enter_provider_boundary,
            # Always classify the result so a lost provider response can keep
            # its provisional link valid even for a direct/admin resend.
            "raise_provider_errors": True,
        }
        if _send_via_ses(**send_kwargs):
            provider_accepted = True
            logger.info("Ticket email sent via SES for registration %s", registration.pk)
        else:
            raise RuntimeError("Ticket email delivery via AWS SES failed or is not configured.")

        from apps.mail.services.login_links import revoke_login_links

        with transaction.atomic():
            if issued_login_link is not None:
                revoke_login_links(registration.login_tokens.exclude(pk=issued_login_link.pk))
            registration.ticket_email_sent_at = timezone.now()
            registration.ticket_email_error = ""
            registration.save(update_fields=["ticket_email_sent_at", "ticket_email_error"])
    except Exception as exc:
        from apps.core.services.aws.provider_outcomes import (
            PROVIDER_OUTCOME_PERMANENT,
            PROVIDER_OUTCOME_TRANSIENT,
            ProviderDeliveryError,
        )
        from apps.core.services.background_jobs import JobClaimLost

        definitive_provider_error = isinstance(exc, ProviderDeliveryError) and exc.outcome in {
            PROVIDER_OUTCOME_PERMANENT,
            PROVIDER_OUTCOME_TRANSIENT,
        }
        delivery_may_have_occurred = provider_accepted or (
            provider_boundary_entered and not definitive_provider_error and not isinstance(exc, JobClaimLost)
        )
        reported_exc = (
            RuntimeError("Ticket email delivery via AWS SES failed.")
            if isinstance(exc, ProviderDeliveryError) and not raise_provider_errors
            else exc
        )
        if issued_login_link is not None and not delivery_may_have_occurred:
            try:
                type(issued_login_link).objects.filter(pk=issued_login_link.pk).delete()
            except Exception:  # noqa: BLE001 - preserve the original delivery error.
                logger.exception("Unable to discard provisional ticket login link")

        if isinstance(exc, JobClaimLost):
            logger.info("Ticket email job claim was lost for registration %s", registration.pk)
        else:
            logger.exception("Failed to send ticket email for registration %s", registration.pk)
            registration.ticket_email_error = str(reported_exc)
            registration.save(update_fields=["ticket_email_error"])
        if reported_exc is not exc:
            raise reported_exc from exc
        raise

"""
Ticket confirmation email service.

Sends a branded HTML email with an inline PDF417 barcode image.
Uses AWS SES through the shared Notification Delivery configuration.
"""

import logging
from urllib.parse import quote

from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.services.aws.provider_outcomes import NO_PROVIDER_RETRIES, ProviderDeliveryError
from apps.core.services.email import EmailAttachment, EmailDeliveryError, EmailMessage, deliver_email
from apps.event.models import EventRegistration
from apps.event.services.ticket.assets import generate_ticket_barcode_png_bytes
from apps.event.services.ticket.calendar import build_google_calendar_url, generate_ics
from apps.event.services.ticket.date_ranges import format_event_date_range

logger = logging.getLogger(__name__)


def _load_config():
    from apps.core.models import EmailServiceConfig

    return EmailServiceConfig.load()


def _build_mime_message(*, subject, from_address, recipients, html_body, barcode_bytes, ics_data):
    """Build the provider-neutral ticket message with PDF417 and ICS attachments."""
    del from_address  # The active provider owns the configured sender address.
    return EmailMessage(
        subject=subject,
        to=tuple(recipients),
        html_body=html_body,
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


def _send_via_ses(
    *,
    config,
    mime_message,
    before_provider_call=None,
    raise_provider_errors: bool = False,
) -> bool:
    """Attempt delivery through the central email facade. Returns True on success."""
    if not config.delivery_configured:
        return False
    try:
        deliver_email(
            mime_message,
            config=config,
            before_provider_call=before_provider_call,
            retry_config=NO_PROVIDER_RETRIES,
        )
        return True
    except EmailDeliveryError as exc:
        logger.exception("Ticket email delivery failed")
        if raise_provider_errors:
            raise ProviderDeliveryError(str(exc), outcome=exc.outcome) from exc
        return False


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
        if not config.delivery_configured:
            raise RuntimeError("Ticket email delivery provider failed or is not configured.")

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
            logger.info("Ticket email accepted for registration %s", registration.pk)
        else:
            raise RuntimeError("Ticket email delivery provider failed or is not configured.")

        from apps.mail.services.tokens.login_links import revoke_login_links

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
            RuntimeError("Ticket email delivery provider failed.")
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

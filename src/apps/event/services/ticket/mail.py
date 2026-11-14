"""
Ticket confirmation email service.

Sends a branded HTML email with an inline PDF417 barcode image.
Uses AWS SES through the shared Notification Delivery configuration.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.core.services.aws.provider_outcomes import NO_PROVIDER_RETRIES, ProviderDeliveryError
from apps.core.services.email import (
    EmailDeliveryError,
    deliver_email,
    email_tracking,
)
from apps.event.models import EventRegistration

from .message import (
    _build_ticket_message,
    _prepare_ticket_login_link,
    # Re-exported: mail.services.sms.ticket imports it from here (lazily, inside a function).
    ticket_login_redirect_path,  # noqa: F401
)

logger = logging.getLogger(__name__)


def _load_config():
    from apps.core.models import EmailServiceConfig

    return EmailServiceConfig.load()


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
            raise ProviderDeliveryError(str(exc), outcome=exc.outcome, retry_after=exc.retry_after) from exc
        return False


class _TicketDelivery:
    """What one send has done so far, which decides how a failure is recorded."""

    def __init__(self, registration: EventRegistration, before_provider_call):
        self.registration = registration
        self.before_provider_call = before_provider_call
        self.issued_login_link = None
        self.provider_accepted = False
        self.provider_boundary_entered = False

    def enter_provider_boundary(self) -> None:
        if self.before_provider_call is not None:
            self.before_provider_call()
        self.provider_boundary_entered = True

    def may_have_delivered(self, exc: Exception) -> bool:
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
        return self.provider_accepted or (
            self.provider_boundary_entered and not definitive_provider_error and not isinstance(exc, JobClaimLost)
        )


def _deliver_ticket(delivery: _TicketDelivery, *, before_token_mutation) -> None:
    registration = delivery.registration
    config = _load_config()
    if not config.delivery_configured:
        raise RuntimeError("Ticket email delivery provider failed or is not configured.")

    # The callback locks and verifies a durable-job claim. Keeping it in the
    # same transaction as token creation prevents recovery from replacing
    # the claim between the fence and this side effect.
    with transaction.atomic():
        if before_token_mutation is not None:
            before_token_mutation()
        login_url, delivery.issued_login_link = _prepare_ticket_login_link(registration)

    mime_message = _build_ticket_message(registration, config=config, login_url=login_url)
    send_kwargs = {
        "config": config,
        "mime_message": mime_message,
        "before_provider_call": delivery.enter_provider_boundary,
        # Always classify the result so a lost provider response can keep
        # its provisional link valid even for a direct/admin resend.
        "raise_provider_errors": True,
    }
    with email_tracking(category="event_ticket", source_type="event.eventregistration", source_id=registration.pk):
        sent = _send_via_ses(**send_kwargs)
    if not sent:
        raise RuntimeError("Ticket email delivery provider failed or is not configured.")
    delivery.provider_accepted = True
    logger.info("Ticket email accepted for registration %s", registration.pk)

    from apps.mail.services.tokens.login_links import revoke_login_links

    with transaction.atomic():
        if delivery.issued_login_link is not None:
            revoke_login_links(registration.login_tokens.exclude(pk=delivery.issued_login_link.pk))
        registration.ticket_email_sent_at = timezone.now()
        registration.ticket_email_error = ""
        registration.save(update_fields=["ticket_email_sent_at", "ticket_email_error"])


def _record_ticket_failure(delivery: _TicketDelivery, exc: Exception, reported_exc: Exception) -> None:
    """Discard a provisional login link that cannot have been delivered, and store the error."""
    from apps.core.services.background_jobs import JobClaimLost

    registration = delivery.registration
    issued_login_link = delivery.issued_login_link
    if issued_login_link is not None and not delivery.may_have_delivered(exc):
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
    delivery = _TicketDelivery(registration, before_provider_call)
    try:
        _deliver_ticket(delivery, before_token_mutation=before_token_mutation)
    except Exception as exc:
        from apps.core.services.aws.provider_outcomes import ProviderDeliveryError

        reported_exc = (
            RuntimeError("Ticket email delivery provider failed.")
            if isinstance(exc, ProviderDeliveryError) and not raise_provider_errors
            else exc
        )
        _record_ticket_failure(delivery, exc, reported_exc)
        if reported_exc is not exc:
            raise reported_exc from exc
        raise

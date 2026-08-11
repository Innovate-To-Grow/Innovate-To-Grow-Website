from django.db import transaction

from apps.core.services.helpers.in_process import start_in_process_task
from apps.event.services.registration_sheet_sync import schedule_registration_sync

INITIAL_TICKET_START_ERROR = "Ticket email could not be started. Check server logs for details."


def send_initial_ticket_email(registration) -> None:
    from apps.core.services.background_jobs import enqueue_job, jobs_enabled

    schedule_registration_sync(registration.event, trigger_id=registration.pk)
    if jobs_enabled():
        enqueue_job(
            kind="event.ticket_email",
            dedupe_key=f"{registration.pk}:initial",
            payload={"registration_id": str(registration.pk)},
            can_retry_after_claim=False,
        )
        return

    registration_id = registration.pk
    transaction.on_commit(
        lambda: _start_ticket_email_in_process(registration_id),
        robust=True,
    )


def _start_ticket_email_in_process(registration_id) -> None:
    """Start a best-effort ticket send without breaking the committed request."""

    thread = start_in_process_task(
        _send_ticket_email_in_process,
        registration_id,
        name=f"initial-ticket-email-{registration_id}",
        daemon=False,
        best_effort_start=True,
    )
    if thread is not None:
        return

    import apps.event.views.registration as registration_api
    from apps.event.models import EventRegistration

    try:
        EventRegistration.objects.filter(pk=registration_id).update(
            ticket_email_error=INITIAL_TICKET_START_ERROR,
        )
    except Exception:
        registration_api.logger.warning(
            "Failed to record initial ticket email startup error",
            exc_info=True,
        )


def _send_ticket_email_in_process(registration_id) -> None:
    import apps.event.views.registration as registration_api
    from apps.event.models import EventRegistration
    from apps.event.services.ticket_mail import send_ticket_email

    try:
        registration = EventRegistration.objects.select_related("event", "ticket", "member").get(pk=registration_id)
        send_ticket_email(registration)
    except Exception:
        registration_api.logger.warning(
            "Failed to send initial ticket email",
            exc_info=True,
        )

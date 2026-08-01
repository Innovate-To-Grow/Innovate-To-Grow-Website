from django.db import transaction

from apps.event.services.registration_sheet_sync import schedule_registration_sync


def send_initial_ticket_email(registration) -> None:
    import apps.event.views.registration as registration_api
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

    def send_after_commit():
        try:
            from apps.event.services.ticket_mail import send_ticket_email

            send_ticket_email(registration)
        except Exception:
            registration_api.logger.warning(
                "Failed to send initial ticket email",
                exc_info=True,
            )

    transaction.on_commit(send_after_commit)

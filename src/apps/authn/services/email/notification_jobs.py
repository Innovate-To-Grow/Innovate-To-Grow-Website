"""Fire-and-forget notification emails, sent by the durable background worker."""

import uuid

from apps.core.services.background_jobs import enqueue_job
from apps.core.services.background_jobs.delivery import provider_call_guard, provider_job_error, wait_for_email_slot

NOTIFICATION_EMAIL_JOB_KIND = "authn.notification_email"


def enqueue_notification_email(
    *,
    recipient: str,
    subject: str,
    template: str,
    context: dict,
    dedupe_key: str | None = None,
):
    """Queue a fire-and-forget notification email without exposing its body in logs."""
    payload = {
        "recipient": recipient,
        "subject": subject,
        "template": template,
        "context": context,
    }
    return enqueue_job(
        kind=NOTIFICATION_EMAIL_JOB_KIND,
        # A job is idempotent across worker retries, but two identical security
        # events at different times must each notify the owner.
        dedupe_key=dedupe_key or str(uuid.uuid4()),
        payload=payload,
        can_retry_after_claim=False,
    )


def send_notification_email_job(job) -> None:
    from apps.authn.services.email.send_email import send_notification_email
    from apps.core.services.aws.provider_outcomes import ProviderDeliveryError

    wait_for_email_slot()
    try:
        sent = send_notification_email(
            **job.payload,
            before_provider_call=provider_call_guard(job),
            raise_provider_errors=True,
        )
    except ProviderDeliveryError as exc:
        raise provider_job_error(exc) from exc
    if not sent:
        raise RuntimeError("SES did not confirm notification delivery.")

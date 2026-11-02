"""Background-job handler that sends a registration's ticket email (on the transactional lane; the email facade
paces it, and a deferral reruns the job at its slot)."""

from apps.core.services.background_jobs.delivery import provider_call_guard, provider_job_error


def send_ticket_email_job(job) -> None:
    from apps.core.models import BackgroundJob
    from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
    from apps.core.services.background_jobs import JobClaimLost
    from apps.event.models import EventRegistration
    from apps.event.services.ticket.mail import send_ticket_email

    registration = EventRegistration.objects.select_related("event", "ticket", "member").get(
        pk=job.payload["registration_id"]
    )

    def fence_token_mutation():
        owns_claim = BackgroundJob.objects.select_for_update().filter(
            pk=job.pk,
            status=BackgroundJob.Status.PROCESSING,
            claim_token=job.claim_token,
        )
        if not owns_claim.exists():
            raise JobClaimLost("Background job claim was lost before login-link issuance.")

    try:
        send_ticket_email(
            registration,
            before_token_mutation=fence_token_mutation,
            before_provider_call=provider_call_guard(job),
            raise_provider_errors=True,
        )
    except ProviderDeliveryError as exc:
        raise provider_job_error(exc) from exc

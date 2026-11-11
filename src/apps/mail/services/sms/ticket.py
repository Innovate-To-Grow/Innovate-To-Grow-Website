"""Ticket texts: a phone-only registrant (no email address on the registration) gets their ticket link by SMS.

Off by default (Mail → SMS Settings, "Text tickets to phone-only registrants", which needs links in SMS). When a
registration's first ticket goes out (``apps.event.signals.initial_ticket_issued``) for a registrant without an
email address but with a verified phone, a ``TicketSms`` row and its job are added in the registration's transaction,
due when SMS quiet hours end. The job sends the text on the transactional lane: the ticket link signs the member in
when personal links are on (otherwise it opens the sign-in page, which returns to the ticket), and the opt-out footer
is added. A number on the opt-out list is never texted. Without background jobs it is sent in-process after the
commit, or skipped during quiet hours (the ticket is in the member's account either way).
"""

import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_UNCERTAIN
from apps.core.services.aws.sms_errors import SmsDeliveryError, SmsOptedOut
from apps.core.services.aws.sms_send import send_text_message
from apps.core.services.background_jobs import DeferredJobError, enqueue_job, jobs_enabled
from apps.core.services.background_jobs.delivery import deferral_of, provider_call_guard, provider_job_error
from apps.core.services.delivery_rates import Lane, WaitMode, wait_mode
from apps.core.services.helpers.in_process import start_in_process_task
from apps.mail.models import SmsConfig, SmsLinkToken, TicketSms

from ..campaign.personalize import personalize
from .compose import apply_footer
from .links import Purpose, issue_personal_link, issue_redirect_link, may_sign_in_by_sms, revoke_links, sign_in_path
from .opt_outs import SKIPPED_MESSAGE, is_opted_out, normalize_phone
from .quiet_hours import HELD_LOG_MESSAGE, held_until, next_send_time

logger = logging.getLogger(__name__)

JOB_KIND = "mail.ticket_sms"
Status = TicketSms.Status
TURNED_OFF_MESSAGE = "Not sent: ticket texts (or links in SMS) were turned off before it went out."
QUIET_NO_JOBS_MESSAGE = "Not sent: it was SMS quiet hours and background jobs are off. The ticket is in the account."


def ticket_texts_on(config: SmsConfig) -> bool:
    return config.ticket_sms_enabled and config.links_enabled


def ticket_phone(registration) -> str:
    """The verified number the ticket text goes to: the phone verified for this registration, else the member's
    verified contact phone (subscribed first); "" when there is none."""
    if registration.phone_verified and normalize_phone(registration.attendee_phone):
        return normalize_phone(registration.attendee_phone)
    phones = [phone for phone in registration.member.contact_phones.all() if phone.verified]
    phones.sort(key=lambda phone: (not phone.subscribe, phone.created_at))
    return normalize_phone(phones[0].to_e164()) if phones else ""


def queue_ticket_sms(sender=None, *, registration, **kwargs) -> TicketSms | None:
    """Receiver of ``initial_ticket_issued``. Never raises: a failure here (rolled back to its savepoint) must not
    undo the registration it belongs to."""
    try:
        with transaction.atomic():
            return _queue(registration)
    except Exception:  # noqa: BLE001 - the registration must still commit.
        logger.exception("Could not queue the ticket text of registration %s", getattr(registration, "pk", None))
        return None


def _queue(registration) -> TicketSms | None:
    config = SmsConfig.load()
    if not ticket_texts_on(config) or (registration.attendee_email or "").strip():
        return None
    phone = ticket_phone(registration)
    if not phone:
        return None
    available_at = next_send_time(config=config)
    record, created = TicketSms.objects.get_or_create(
        registration=registration, defaults={"phone_number": phone, "available_at": available_at}
    )
    if not created:
        return record
    if jobs_enabled():
        enqueue_job(
            kind=JOB_KIND,
            dedupe_key=str(record.pk),
            payload={"ticket_sms_id": str(record.pk)},
            can_retry_after_claim=False,
            available_at=available_at,
        )
    else:
        record_id = record.pk
        transaction.on_commit(lambda: _start_in_process(record_id), robust=True)
    return record


def _start_in_process(record_id) -> None:
    start_in_process_task(
        _send_in_process, record_id, name=f"ticket-sms-{record_id}", daemon=False, best_effort_start=True
    )


def _send_in_process(record_id) -> None:
    try:
        record = TicketSms.objects.select_related("registration__event", "registration__member").get(pk=record_id)
        with wait_mode(WaitMode.DEDICATED):
            deliver_ticket_sms(record)
    except Exception:  # noqa: BLE001 - a best-effort thread; the row keeps what is known.
        logger.exception("Ticket text %s could not be sent in-process", record_id)


def send_ticket_sms_job(job) -> None:
    record = TicketSms.objects.select_related("registration__event", "registration__member").get(
        pk=job.payload["ticket_sms_id"]
    )
    deliver_ticket_sms(record, job=job)


def deliver_ticket_sms(record: TicketSms, *, job=None) -> None:
    """Send ``record``'s ticket text once (``job``: the queued job, which then owns retries)."""
    if record.status != Status.PENDING:
        return
    config = SmsConfig.load()
    if not ticket_texts_on(config):
        return _finish(record, Status.SKIPPED, TURNED_OFF_MESSAGE)
    until = held_until(config=config)
    if until is not None:
        if job is None:
            return _finish(record, Status.SKIPPED, QUIET_NO_JOBS_MESSAGE)
        _note(record, available_at=until, error_message=HELD_LOG_MESSAGE)
        raise DeferredJobError(HELD_LOG_MESSAGE, until=until)
    if is_opted_out(record.phone_number):
        return _finish(record, Status.OPTED_OUT, SKIPPED_MESSAGE)
    links = SmsLinkToken.objects.filter(registration=record.registration, purpose=Purpose.TICKET)
    revoke_links(links)
    body = ticket_text(record.registration, _ticket_link(record.registration, config), config)
    TicketSms.objects.filter(pk=record.pk).update(attempts=F("attempts") + 1, updated_at=timezone.now())
    try:
        message_id = send_text_message(
            record.phone_number,
            body,
            lane=Lane.TRANSACTIONAL,
            before_provider_call=provider_call_guard(job) if job is not None else None,
        )
    except SmsOptedOut:
        revoke_links(links)
        return _finish(record, Status.OPTED_OUT, SKIPPED_MESSAGE)
    except SmsDeliveryError as exc:
        _record_failure(record, exc, links, job=job)
        if job is not None:
            raise provider_job_error(exc) from exc
        return None
    return _finish(record, Status.SENT, "", message_id=message_id, sent_at=timezone.now())


def ticket_text(registration, link: str, config: SmsConfig) -> str:
    values = {
        "first_name": registration.attendee_first_name or registration.member.first_name or "",
        "event_name": registration.event.name,
        "ticket_link": link,
    }
    return apply_footer(personalize(config.ticket_sms_template, values), config)


def _ticket_link(registration, config: SmsConfig) -> str:
    from apps.event.services.ticket.mail import ticket_login_redirect_path

    destination = ticket_login_redirect_path(registration)
    days = config.ticket_link_validity_days
    if config.personal_links_enabled and may_sign_in_by_sms(registration.member):
        return issue_personal_link(
            purpose=Purpose.TICKET,
            member=registration.member,
            redirect_path=destination,
            validity_days=days,
            registration=registration,
        )
    return issue_redirect_link(
        purpose=Purpose.TICKET, redirect_path=sign_in_path(destination), validity_days=days, registration=registration
    )


def _record_failure(record: TicketSms, exc: SmsDeliveryError, links, *, job) -> None:
    """What a failed send leaves: a link that cannot have arrived is revoked; the row ends failed or uncertain unless
    the job will try again (held back, or a temporary error with attempts left)."""
    uncertain = exc.outcome == PROVIDER_OUTCOME_UNCERTAIN and deferral_of(exc) is None
    if not uncertain:
        revoke_links(links)
    retried = job is not None and (deferral_of(exc) is not None or _retry_left(exc, job))
    if retried:
        return _note(record, error_message=str(exc))
    return _finish(record, Status.UNCERTAIN if uncertain else Status.FAILED, str(exc))


def _retry_left(exc: SmsDeliveryError, job) -> bool:
    from apps.core.services.background_jobs import TransientJobError

    return isinstance(provider_job_error(exc), TransientJobError) and job.attempts < job.max_attempts


def _note(record: TicketSms, **values) -> None:
    values["error_message"] = values.get("error_message", "")[:300]
    TicketSms.objects.filter(pk=record.pk, status=Status.PENDING).update(**values, updated_at=timezone.now())


def _finish(record: TicketSms, status: str, message: str, **values) -> None:
    TicketSms.objects.filter(pk=record.pk, status=Status.PENDING).update(
        status=status, error_message=message[:300], updated_at=timezone.now(), **values
    )
    record.refresh_from_db()

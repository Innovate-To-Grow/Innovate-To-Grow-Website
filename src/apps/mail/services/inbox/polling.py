"""The inbox poller: checks every inbox account for new mail in the durable background worker, whether or not anyone
has the inbox open. Job kind ``mail.inbox_poll``, one job per poll, each queueing the next.

Every ``health.poll_interval_seconds()`` (``MAIL_INBOX_POLL_SECONDS``, 3 minutes by default; 0 turns polling off) a
poll reads each account's newest Inbox messages and records them, with whether the account connected, in
``InboxAccountState`` (``health``): the admin inbox then lists from that snapshot without connecting, hides accounts
that cannot connect, and the sidebar shows the unread count.

Gmail IMAP is read incrementally so a poll every few minutes stays far below Gmail's daily IMAP download limit:
two UID searches (numbers only) find the newest messages and the unread ones, and only messages the snapshot does
not hold yet are downloaded. Microsoft Graph lists return previews only, so they are read whole. Every read goes
through the delivery-rate limiter like the inbox's own reads.

``ensure_scheduled`` (the worker's maintenance, at start-up and on its interval) restarts the chain if it broke. A
job has one attempt: the next poll is its retry. Overlapping jobs are harmless (each poll is independent).
"""

import logging
from datetime import datetime, timedelta

from django.utils import timezone
from imap_tools import AND

from apps.core.models import BackgroundJob

from . import graph_backend, health
from .accounts import readable_accounts
from .connection import INBOX_FOLDER, InboxError

logger = logging.getLogger(__name__)

POLL_JOB_KIND = "mail.inbox_poll"
_WAITING = (BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY)
_FINISHED = (BackgroundJob.Status.SUCCEEDED, BackgroundJob.Status.FAILED, BackgroundJob.Status.CANCELLED)
FINISHED_JOB_RETENTION = timedelta(days=1)


def register() -> None:
    """Called from ``MailConfig.ready``."""
    from apps.core.services.background_jobs import register_job_kind

    register_job_kind(POLL_JOB_KIND, handler="apps.mail.services.inbox.polling.run_poll_job")


def enabled() -> bool:
    return health.poll_interval_seconds() > 0


def _waiting(*statuses) -> bool:
    return BackgroundJob.objects.filter(kind=POLL_JOB_KIND, status__in=(*_WAITING, *statuses)).exists()


def _enqueue(available_at: datetime, label: str) -> bool:
    from apps.core.services.background_jobs import enqueue_job

    _job, created = enqueue_job(
        kind=POLL_JOB_KIND,
        dedupe_key=f"{label}:{available_at.isoformat()}",
        payload={"requested": label},
        max_attempts=1,
        available_at=available_at,
    )
    return created


def ensure_scheduled(*, now: datetime | None = None) -> bool:
    """Queue a poll now unless one is waiting or running (or polling is off); True when one was queued."""
    if not enabled() or _waiting(BackgroundJob.Status.PROCESSING):
        return False
    return _enqueue(now or timezone.now(), "scheduled")


def run_poll_job(job) -> None:
    try:
        poll_accounts()
    finally:
        if enabled() and not _waiting():
            _enqueue(timezone.now() + timedelta(seconds=health.poll_interval_seconds()), "scheduled")


def poll_accounts(*, should_stop=None) -> dict[str, int]:
    """Read every inbox account once and record the outcome; returns how many connected, failed and were pruned."""
    accounts = readable_accounts(use_cache=False)
    result = {"connected": 0, "failed": 0, "pruned": health.prune(accounts)}
    states = health.states_for(accounts)
    for account in accounts:
        if should_stop is not None and should_stop():
            break
        previous = states.get(account.key)
        try:
            messages = _poll_account(account, list(previous.messages or []) if previous else [])
        except InboxError as exc:
            logger.warning("Inbox poll could not read %s: %s", account.key, exc)
            health.record_failure(account, exc)
            result["failed"] += 1
            continue
        except Exception as exc:
            logger.exception("Inbox poll failed for %s.", account.key)
            health.record_failure(account, exc)
            result["failed"] += 1
            continue
        for message in messages:
            message["account"] = account.key
            message["account_address"] = account.address
        health.record_ok(account, messages=messages)
        result["connected"] += 1
    return result


def _poll_account(account, previous: list[dict]) -> list[dict]:
    if account.is_graph:
        reader = graph_backend.reader_for(account.address)
        return graph_backend.list_messages(reader, folder=INBOX_FOLDER, limit=health.SNAPSHOT_LIMIT)
    return _poll_imap(account, previous)


def _poll_imap(account, previous: list[dict]) -> list[dict]:
    import apps.mail.services.inbox as inbox_api

    from .messages import message_summary

    known = {str(message.get("uid")): message for message in previous if message.get("uid")}
    try:
        with inbox_api._open_inbox(folder=INBOX_FOLDER, account=account) as client:
            newest = [str(uid) for uid in client.uids("ALL")][-health.SNAPSHOT_LIMIT :][::-1]
            unseen = {str(uid) for uid in client.uids(AND(seen=False))}
            missing = [uid for uid in newest if uid not in known]
            fetched = {}
            if missing:
                for message in client.fetch(AND(uid=missing), mark_seen=False, bulk=True):
                    summary = message_summary(message)
                    fetched[summary["uid"]] = summary
    except InboxError:
        raise
    except Exception as exc:
        raise InboxError("Failed to poll the inbox.") from exc
    messages = []
    for uid in newest:
        summary = fetched.get(uid) or known.get(uid)
        if summary is None:
            continue  # deleted between the search and the fetch
        messages.append({**summary, "is_seen": uid not in unseen})
    return messages


def purge_finished_jobs(*, now: datetime | None = None) -> int:
    """Delete finished poll jobs older than a day (one is queued every interval)."""
    cutoff = (now or timezone.now()) - FINISHED_JOB_RETENTION
    deleted, _ = BackgroundJob.objects.filter(
        kind=POLL_JOB_KIND, status__in=_FINISHED, completed_at__lt=cutoff
    ).delete()
    return deleted

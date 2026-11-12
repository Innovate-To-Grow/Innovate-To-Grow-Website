"""Sync AWS's opted-out list into the SMS opt-out list (Mail → SMS Opt-outs). AWS is only read, never changed.

Each run reads the sending number's opted-out list (``core.services.aws.sms_opt_outs.read_opted_out_list``), then:

- adds every listed number as an ``aws`` opt-out (or reopens it when it had opted back in), confirms a
  ``send_refusal`` row as ``aws``, and unsubscribes the members' matching phones once;
- stamps every active row AWS still lists as seen;
- after a complete read only, clears the ``aws`` and ``send_refusal`` rows AWS no longer lists (the person replied
  START). A staff row is never cleared here, and a partial read (a list longer than one run reads) clears nothing.

The background worker runs it in its hourly maintenance (``run_scheduled``); staff can run it from the admin.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.core.models import AWSCredentialConfig
from apps.core.services.aws.credentials import AwsCredentialsError
from apps.core.services.aws.sms_opt_outs import OptedOutList, OptOutListError, read_opted_out_list
from apps.mail.models import SmsConfig, SmsOptOut, SmsOptOutSyncState

from .opt_outs import active_opt_outs, normalize_phone, open_opt_out, unsubscribe_contact_phones

logger = logging.getLogger(__name__)

Status = SmsOptOutSyncState.Status
_CHUNK = 500


@dataclass(frozen=True)
class SyncResult:
    status: str
    message: str = ""
    list_name: str = ""
    listed: int = 0
    added: int = 0
    cleared: int = 0


def run_scheduled(should_stop=None) -> SyncResult | None:
    """The worker's hourly run: only while the sync is on in SMS Settings."""
    if not SmsConfig.load().opt_out_sync_enabled:
        return None
    return sync_opt_outs()


def sync_opt_outs(*, now=None) -> SyncResult:
    """Read AWS's list and apply it; the outcome is also recorded on ``SmsOptOutSyncState``."""
    started_at = now or timezone.now()
    config = SmsConfig.load()
    aws = AWSCredentialConfig.load()
    if not aws.is_configured:
        return _finish(SyncResult(Status.NOT_CONFIGURED, "AWS credentials are not configured."), started_at)
    policy = settings.SMS_POLICY
    try:
        listing = read_opted_out_list(
            origination=aws.sms_from_number.strip(),
            list_name=config.opt_out_list_name.strip(),
            page_size=policy["opt_out_page_size"],
            max_pages=policy["opt_out_max_pages"],
            timeout=policy["opt_out_request_timeout_seconds"],
        )
    except AwsCredentialsError:
        return _finish(SyncResult(Status.NOT_CONFIGURED, "AWS credentials are not configured."), started_at)
    except OptOutListError as exc:
        detail = f"{exc} ({exc.code})" if exc.code else str(exc)
        return _finish(SyncResult(Status.FAILED, detail), started_at)
    return _finish(_apply(listing, started_at), started_at)


def _apply(listing: OptedOutList, started_at) -> SyncResult:
    entries = {}
    for entry in listing.numbers:
        number = normalize_phone(entry.phone_number)
        if number:
            entries.setdefault(number, entry)
    added = _add_listed(entries, started_at)
    _confirm_listed(list(entries), started_at)
    cleared = _clear_unlisted(started_at) if listing.complete else 0
    if listing.complete:
        status, message = Status.OK, ""
    else:
        status = Status.PARTIAL
        message = "AWS's list is longer than one run reads: nothing was cleared. Raise SMS_POLICY opt_out_max_pages."
    return SyncResult(status, message, list_name=listing.list_name, listed=len(entries), added=added, cleared=cleared)


def _chunks(values: list):
    for start in range(0, len(values), _CHUNK):
        yield values[start : start + _CHUNK]


def _add_listed(entries: dict, started_at) -> int:
    """Create the listed numbers the list lacks and reopen the ones that had opted back in; how many."""
    added = 0
    for chunk in _chunks(list(entries)):
        existing = {row.phone_number: row for row in SmsOptOut.objects.filter(phone_number__in=chunk)}
        new_rows = [
            SmsOptOut(
                phone_number=number,
                source=SmsOptOut.Source.AWS,
                opted_out_at=entries[number].opted_out_at or started_at,
                end_user_opted_out=entries[number].end_user_opted_out,
                last_seen_in_aws_at=started_at,
            )
            for number in chunk
            if number not in existing
        ]
        # A send refused meanwhile may have added one of them: that row stays and is confirmed below.
        SmsOptOut.objects.bulk_create(new_rows, ignore_conflicts=True)
        added += len(new_rows)
        for number, row in existing.items():
            if row.cleared_at is not None:
                entry = entries[number]
                open_opt_out(
                    number,
                    source=SmsOptOut.Source.AWS,
                    opted_out_at=entry.opted_out_at or started_at,
                    end_user_opted_out=entry.end_user_opted_out,
                    last_seen_in_aws_at=started_at,
                )
                added += 1
    return added


def _confirm_listed(numbers: list, started_at) -> None:
    """Stamp the listed active rows as seen, confirm the send refusals, and unsubscribe new opt-outs' phones."""
    for chunk in _chunks(numbers):
        listed = active_opt_outs().filter(phone_number__in=chunk)
        listed.filter(source=SmsOptOut.Source.SEND_REFUSAL).update(source=SmsOptOut.Source.AWS)
        listed.update(last_seen_in_aws_at=started_at, updated_at=timezone.now())
        for row in listed.filter(contacts_unsubscribed_at__isnull=True):
            unsubscribe_contact_phones(row)


def _clear_unlisted(started_at) -> int:
    """Clear the AWS-sourced rows AWS no longer lists, learned before this run began (a send refused during the
    read is newer than the list and stays)."""
    unlisted = active_opt_outs().filter(
        Q(last_seen_in_aws_at__isnull=True) | Q(last_seen_in_aws_at__lt=started_at),
        source__in=(SmsOptOut.Source.AWS, SmsOptOut.Source.SEND_REFUSAL),
        opted_out_at__lt=started_at,
    )
    return unlisted.update(
        cleared_at=timezone.now(),
        cleared_reason="No longer on AWS's opted-out list (the person opted back in).",
        updated_at=timezone.now(),
    )


def _finish(result: SyncResult, started_at) -> SyncResult:
    state = SmsOptOutSyncState.load()
    values = {"status": result.status, "message": result.message[:300], "last_run_at": started_at}
    if result.status in (Status.OK, Status.PARTIAL):
        values.update(
            list_name=result.list_name[:128],
            last_success_at=started_at,
            listed_count=result.listed,
            added_count=result.added,
            cleared_count=result.cleared,
        )
    SmsOptOutSyncState.objects.filter(pk=state.pk).update(**values, updated_at=timezone.now())
    log = logger.warning if result.status == Status.FAILED else logger.info
    log(
        "SMS opt-out sync: %s (listed %d, added %d, cleared %d)",
        result.status,
        result.listed,
        result.added,
        result.cleared,
    )
    return result

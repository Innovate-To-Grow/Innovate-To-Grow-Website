import logging

from django.utils import timezone

from .logs import record_sync_failure
from .rows import build_header, build_row
from .scheduler import (
    _sync_in_progress,
    _sync_lock,
    _sync_pending,
    schedule_immediate_sync,
)
from .sheets import MemberSyncError

logger = logging.getLogger(__name__)


def sync_members_to_sheet(*, sync_type: str = "full") -> int:
    from authn.models import MemberSheetSyncConfig, MemberSheetSyncLog

    config = MemberSheetSyncConfig.load()
    if not config.is_configured:
        raise MemberSyncError("Member sheet sync is not configured or not enabled.")

    with _sync_lock:
        if _sync_in_progress.is_set():
            _sync_pending.set()
            logger.info("Member sync already in progress in this worker; queued follow-up sync.")
            return 0
        _sync_in_progress.set()

    rows = []
    try:
        rows = _write_members(config)
    except MemberSyncError as exc:
        record_sync_failure(config, str(exc), sync_type=sync_type)
        raise
    except Exception as exc:
        record_sync_failure(config, str(exc), sync_type=sync_type)
        raise MemberSyncError(f"Failed to write to Google Sheet: {exc}") from exc
    finally:
        _finish_active_sync()

    config.synced_at = timezone.now()
    config.sync_count = len(rows)
    config.sync_error = ""
    config.save(update_fields=["synced_at", "sync_count", "sync_error", "updated_at"])

    MemberSheetSyncLog.objects.create(
        sync_type=sync_type,
        status=MemberSheetSyncLog.Status.SUCCESS,
        rows_written=len(rows),
    )
    return len(rows)


def _write_members(config) -> list[list[str]]:
    from django.contrib.auth import get_user_model

    import authn.services.member_sheet_sync as sync_api

    Member = get_user_model()
    members = list(Member.objects.all().prefetch_related("contact_emails", "contact_phones").order_by("date_joined"))
    rows = [build_row(member) for member in members]
    worksheet = sync_api._get_worksheet(config)
    worksheet.clear()
    worksheet.update([build_header()] + rows, value_input_option="USER_ENTERED")
    logger.info("Full member sync: %d rows written to sheet.", len(rows))
    return rows


def _finish_active_sync() -> None:
    should_sync_again = False
    with _sync_lock:
        _sync_in_progress.clear()
        if _sync_pending.is_set():
            _sync_pending.clear()
            should_sync_again = True
    if should_sync_again:
        schedule_immediate_sync()

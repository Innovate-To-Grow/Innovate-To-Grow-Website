"""
Sync member directory to a Google Sheet (one-way: Django -> Sheet).

Full-replace on every run: clear the sheet, then write header + all rows.

Three entry points:
  - schedule_member_sync(): debounced — waits 15s for more saves, then full replace.
  - sync_members_to_sheet(): blocking full replace (admin action / management command).
  - _flush_pending_sync(): internal — executes after debounce timer fires.
"""

import logging
import threading

from django.db import close_old_connections
from django.utils import timezone

from core.models import GoogleCredentialConfig

logger = logging.getLogger(__name__)

_sync_timer: threading.Timer | None = None
_sync_lock = threading.Lock()
_sync_in_progress = threading.Event()
_sync_pending = threading.Event()
DEBOUNCE_SECONDS = 15

# Cells beginning with these characters are interpreted as formulas by Sheets
# under value_input_option="USER_ENTERED". Prefixing with an apostrophe forces
# Sheets to treat the cell as literal text.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _safe(value) -> str:
    s = str(value or "")
    return f"'{s}" if s.startswith(_FORMULA_TRIGGERS) else s


class MemberSyncError(RuntimeError):
    """Raised when member sheet sync fails."""


def _get_worksheet(config):
    """Open the configured worksheet for the member sync."""
    credentials = GoogleCredentialConfig.load()
    if not credentials.is_configured:
        raise MemberSyncError("No active Google service account is configured.")

    import gspread

    client = gspread.service_account_from_dict(credentials.get_credentials_info())
    spreadsheet = client.open_by_key(config.google_sheet_id)

    if config.worksheet_gid is not None:
        worksheet = next((ws for ws in spreadsheet.worksheets() if ws.id == config.worksheet_gid), None)
        if worksheet is None:
            raise MemberSyncError("Worksheet GID not found in the spreadsheet.")
    else:
        worksheet = spreadsheet.sheet1

    return worksheet


def _build_header() -> list[str]:
    return [
        "UUID",
        "First Name",
        "Middle Name",
        "Last Name",
        "Primary Email",
        "Primary Phone",
        "Organization",
        "Title",
        "Date Joined (UTC)",
        "Last Updated (UTC)",
        "Active",
    ]


def _build_row(member) -> list[str]:
    phones = getattr(member, "_prefetched_objects_cache", {}).get("contact_phones")
    if phones is not None:
        primary_phone = phones[0].phone_number if phones else ""
    else:
        phone_obj = member.contact_phones.first()
        primary_phone = phone_obj.phone_number if phone_obj else ""

    return [
        str(member.id),
        _safe(member.first_name),
        _safe(member.middle_name),
        _safe(member.last_name),
        _safe(member.get_primary_email()),
        _safe(primary_phone),
        _safe(member.organization),
        _safe(member.title),
        member.date_joined.strftime("%Y-%m-%d %H:%M"),
        member.updated_at.strftime("%Y-%m-%d %H:%M"),
        "Yes" if member.is_active else "No",
    ]


# ---------------------------------------------------------------------------
# Debounced sync (called on save, collapses bursts into 1 API call)
# ---------------------------------------------------------------------------


def schedule_member_sync() -> None:
    """
    Schedule a full-replace sheet sync after DEBOUNCE_SECONDS.

    If called again within the window the timer resets, so rapid saves
    collapse into a single API call.  Non-blocking — returns immediately.
    """
    global _sync_timer

    from authn.models import MemberSheetSyncConfig

    config = MemberSheetSyncConfig.load()
    if not config.is_configured or not config.auto_sync_enabled:
        return

    with _sync_lock:
        if _sync_timer is not None:
            _sync_timer.cancel()
        _sync_timer = threading.Timer(DEBOUNCE_SECONDS, _flush_pending_sync)
        _sync_timer.daemon = True
        _sync_timer.start()


def _schedule_immediate_sync() -> None:
    """Queue a follow-up sync for changes that arrived during an active write."""
    global _sync_timer

    with _sync_lock:
        if _sync_timer is not None:
            _sync_timer.cancel()
        _sync_timer = threading.Timer(0, _flush_pending_sync)
        _sync_timer.daemon = True
        _sync_timer.start()


def _flush_pending_sync() -> None:
    """Execute the full replace — runs in a background thread after debounce."""
    global _sync_timer

    with _sync_lock:
        _sync_timer = None

    try:
        close_old_connections()
        from authn.models import MemberSheetSyncLog

        sync_members_to_sheet(sync_type=MemberSheetSyncLog.SyncType.DEBOUNCED)
    except Exception:
        logger.exception("Debounced member sheet sync failed.")
    finally:
        close_old_connections()


# ---------------------------------------------------------------------------
# Full sync: replace entire sheet
# ---------------------------------------------------------------------------


def sync_members_to_sheet(*, sync_type: str = "full") -> int:
    """
    Full replace of the Google Sheet with all members.

    Returns the number of member rows written.
    Raises MemberSyncError on failure.
    """
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
        from django.contrib.auth import get_user_model

        Member = get_user_model()
        members = list(
            Member.objects.all().prefetch_related("contact_emails", "contact_phones").order_by("date_joined")
        )
        header = _build_header()
        rows = [_build_row(m) for m in members]

        worksheet = _get_worksheet(config)
        worksheet.clear()
        worksheet.update([header] + rows, value_input_option="USER_ENTERED")
        logger.info("Full member sync: %d rows written to sheet.", len(rows))
    except MemberSyncError as exc:
        _record_sync_failure(config, str(exc), sync_type=sync_type)
        raise
    except Exception as exc:
        _record_sync_failure(config, str(exc), sync_type=sync_type)
        raise MemberSyncError(f"Failed to write to Google Sheet: {exc}") from exc
    finally:
        should_sync_again = False
        with _sync_lock:
            _sync_in_progress.clear()
            if _sync_pending.is_set():
                _sync_pending.clear()
                should_sync_again = True
        if should_sync_again:
            _schedule_immediate_sync()

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


def _record_sync_failure(config, error_message: str, *, sync_type: str) -> None:
    from authn.models import MemberSheetSyncLog

    config.synced_at = timezone.now()
    config.sync_error = error_message
    config.save(update_fields=["synced_at", "sync_error", "updated_at"])

    MemberSheetSyncLog.objects.create(
        sync_type=sync_type,
        status=MemberSheetSyncLog.Status.FAILED,
        rows_written=0,
        error_message=error_message,
    )

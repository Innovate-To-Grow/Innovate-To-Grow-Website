import logging
import threading

from django.db import close_old_connections

logger = logging.getLogger(__name__)

_sync_timer: threading.Timer | None = None
_sync_lock = threading.Lock()
_sync_in_progress = threading.Event()
_sync_pending = threading.Event()


def schedule_member_sync() -> None:
    global _sync_timer

    from authn.models import MemberSheetSyncConfig

    config = MemberSheetSyncConfig.load()
    if not config.is_configured or not config.auto_sync_enabled:
        return

    import authn.services.member_sheet_sync as sync_api

    with _sync_lock:
        if _sync_timer is not None:
            _sync_timer.cancel()
        _sync_timer = sync_api.threading.Timer(
            sync_api.DEBOUNCE_SECONDS,
            _flush_pending_sync,
        )
        _sync_timer.daemon = True
        _sync_timer.start()


def schedule_immediate_sync() -> None:
    global _sync_timer

    import authn.services.member_sheet_sync as sync_api

    with _sync_lock:
        if _sync_timer is not None:
            _sync_timer.cancel()
        _sync_timer = sync_api.threading.Timer(0, _flush_pending_sync)
        _sync_timer.daemon = True
        _sync_timer.start()


def _flush_pending_sync() -> None:
    global _sync_timer

    with _sync_lock:
        _sync_timer = None

    try:
        close_old_connections()
        from authn.models import MemberSheetSyncLog
        from authn.services.member_sheet_sync import sync_members_to_sheet

        sync_members_to_sheet(sync_type=MemberSheetSyncLog.SyncType.DEBOUNCED)
    except Exception:
        logger.exception("Debounced member sheet sync failed.")
    finally:
        close_old_connections()

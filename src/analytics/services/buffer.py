import atexit
import logging
import threading
from collections import deque

from django.db import DatabaseError

from analytics.models import PageView

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100
_FLUSH_INTERVAL = 5  # seconds
_MAX_RETRIES = 2
_MAX_BUFFER_SIZE = 10_000

_buffer: deque[dict] = deque()
_lock = threading.Lock()
_timer: threading.Timer | None = None
_flush_done = threading.Event()  # signaled when no flush is in progress
_flush_done.set()
_initialized = False


def _do_bulk_insert(batch: list[dict]) -> None:
    """Attempt bulk insert with retry. On final failure, drop and log."""
    for attempt in range(_MAX_RETRIES):
        try:
            PageView.objects.bulk_create([PageView(**data) for data in batch])
            return
        except DatabaseError:
            if attempt < _MAX_RETRIES - 1:
                logger.warning("bulk-insert attempt %d failed, retrying…", attempt + 1)
            else:
                logger.exception(
                    "Failed to bulk-insert %d page views after %d attempts — dropping batch",
                    len(batch),
                    _MAX_RETRIES,
                )


def _flush():
    """Drain the buffer and bulk-insert into the database."""
    with _lock:
        if not _flush_done.is_set():
            # Another flush is already in progress; reschedule and skip.
            _schedule_flush_locked()
            return
        if not _buffer:
            _schedule_flush_locked()
            return
        _flush_done.clear()
        batch = list(_buffer)
        _buffer.clear()

    try:
        _do_bulk_insert(batch)
    finally:
        _flush_done.set()
        with _lock:
            _schedule_flush_locked()


def _schedule_flush_locked():
    """Schedule the next periodic flush. Caller MUST hold _lock."""
    global _timer
    if _timer is not None:
        _timer.cancel()
    _timer = threading.Timer(_FLUSH_INTERVAL, _flush)
    _timer.daemon = True
    _timer.start()


def _ensure_initialized():
    """Start the periodic flush timer on first use (lazy init)."""
    global _initialized
    if _initialized:
        return
    _initialized = True
    _schedule_flush_locked()


def enqueue(data: dict) -> None:
    """Add a page-view record to the in-memory buffer.

    Triggers an immediate flush when the buffer reaches _BATCH_SIZE.
    Drops oldest entries if the buffer exceeds _MAX_BUFFER_SIZE.
    """
    with _lock:
        _ensure_initialized()
        _buffer.append(data)

        if len(_buffer) > _MAX_BUFFER_SIZE:
            overflow = len(_buffer) - _MAX_BUFFER_SIZE
            for _ in range(overflow):
                _buffer.popleft()
            logger.warning("Analytics buffer overflow — dropped %d oldest entries", overflow)

        should_flush = len(_buffer) >= _BATCH_SIZE

    if should_flush:
        threading.Thread(target=_flush, daemon=True).start()


def flush_sync() -> None:
    """Immediately flush the buffer. Waits for any in-flight flush to finish first."""
    global _timer, _initialized

    # Wait for any background flush to complete (with timeout to avoid deadlock).
    _flush_done.wait(timeout=10)

    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
        _initialized = False

        if not _buffer:
            return
        batch = list(_buffer)
        _buffer.clear()

    try:
        PageView.objects.bulk_create([PageView(**data) for data in batch])
    except DatabaseError:
        logger.exception("Failed to bulk-insert %d page views on flush_sync", len(batch))


# Ensure remaining records are written when the process exits.
atexit.register(flush_sync)

"""How many web processes share the limits (per-process counter mode only).

Each process keeps one ``RequestLimitProcess`` row. On the request path it refreshes the row and recounts the live
rows at most every ``store.heartbeat_seconds`` (one UPDATE and one COUNT per process per interval, never per
request); a row not refreshed for ``process_expiry_seconds`` no longer counts and is deleted after
``process_prune_seconds``. The count includes this process, so it is never below 1. A database error keeps the
previous count (fail open: the limits are only less divided).
"""

import logging
import os
import socket
import threading
import uuid

from django.db import DatabaseError

from apps.core.models import RequestLimitProcess

from .context import as_datetime, section

logger = logging.getLogger(__name__)


class _Process:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.pid = os.getpid()
        self.instance = uuid.uuid4().hex
        self.started_at = None
        self.count = 1
        self.refreshed_at = None
        self.pruned_at = None


PROCESS = _Process()


def _refresh(now: float) -> None:
    store = section("store")
    if PROCESS.started_at is None:
        PROCESS.started_at = now
    seen = as_datetime(now)
    updated = RequestLimitProcess.objects.filter(instance=PROCESS.instance).update(last_seen=seen)
    if not updated:
        RequestLimitProcess.objects.create(
            instance=PROCESS.instance,
            host=socket.gethostname()[:255],
            pid=PROCESS.pid,
            started_at=as_datetime(PROCESS.started_at),
            last_seen=seen,
        )
    live = RequestLimitProcess.objects.filter(last_seen__gte=as_datetime(now - store["process_expiry_seconds"]))
    PROCESS.count = max(1, live.count())
    if PROCESS.pruned_at is None or now - PROCESS.pruned_at >= store["process_prune_seconds"]:
        PROCESS.pruned_at = now
        RequestLimitProcess.objects.filter(last_seen__lt=as_datetime(now - store["process_prune_seconds"])).delete()


def live_processes(now: float) -> int:
    """The live web processes, this one included (at least 1)."""
    if os.getpid() != PROCESS.pid:  # a forked child must not reuse its parent's row
        PROCESS.reset()
    due = PROCESS.refreshed_at is None or now - PROCESS.refreshed_at >= section("store")["heartbeat_seconds"]
    # One thread refreshes; the others keep using the current count instead of waiting for it.
    if due and PROCESS.lock.acquire(blocking=False):
        try:
            PROCESS.refreshed_at = now
            _refresh(now)
        except DatabaseError:
            logger.warning("request_limits.heartbeat_failed", exc_info=True)
        finally:
            PROCESS.lock.release()
    return PROCESS.count

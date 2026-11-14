"""Serialize everything that happens to one phone number across concurrent requests (sending lives in ``sns_verify``).

A process-local lock always applies; on PostgreSQL a session advisory lock keyed on the number makes it hold across
processes too.
"""

from __future__ import annotations

import hashlib
import threading
from contextlib import contextmanager

from django.db import connection

_LOCAL_PHONE_LOCKS = tuple(threading.Lock() for _ in range(64))


def _phone_lock_id(phone_number: str) -> int:
    digest = hashlib.sha256(phone_number.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


@contextmanager
def _lock_phone(phone_number: str):
    """Serialize one phone across reservation, provider call, and finalization."""
    lock_id = _phone_lock_id(phone_number)
    local_lock = _LOCAL_PHONE_LOCKS[abs(lock_id) % len(_LOCAL_PHONE_LOCKS)]
    with local_lock:
        if connection.vendor != "postgresql":
            yield
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [lock_id])
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])

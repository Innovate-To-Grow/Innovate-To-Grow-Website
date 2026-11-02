"""Periodic delivery-rate upkeep, run by the background worker's maintenance loop.

Re-reads the provider limits that are due (the identities in use first, so Smart rate knows them before their next
send), and deletes usage buckets past their retention and the state of identities no longer in use.
"""

from dataclasses import dataclass

from .families import active_target, registered_families
from .runtime import budget, context
from .runtime.discovery import READERS, refresh_discovery
from .runtime.state import purge_idle


@dataclass(frozen=True)
class MaintenanceResult:
    limits_read: int
    buckets_purged: int
    states_purged: int


def run_maintenance() -> MaintenanceResult:
    read = 0
    for family in registered_families():
        target = active_target(family)
        if target is not None and target.channel in READERS:
            read += refresh_discovery(target.channel, target.identity)
    for channel in READERS:
        read += refresh_discovery(channel)
    now = context.clock()
    return MaintenanceResult(limits_read=read, buckets_purged=budget.purge(now), states_purged=purge_idle(now))

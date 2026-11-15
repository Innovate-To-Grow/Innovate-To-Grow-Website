"""Apps that list the mailbox's Inbox on their own schedule, so the Email Monitoring card can show every cadence.

Bounce processing lists the Inbox for reports on its own schedule and checkpoint. An app that lists the same Inbox
separately (the helpdesk's intake, which records every message in the inbound queue) registers here from its
``AppConfig.ready()`` with the dotted path of a zero-argument callable that describes it (``InboxReader``). The
Email Monitoring card shows each reader beside the bounce scan, so the page says how often the mailbox is really
read, and links to the reader's own controls: the "the app registers, core calls back by name" pattern of job kinds
and ``CSP_FRAME_HOST_PROVIDERS``, so neither ``core`` nor ``mail`` imports a business app. ``format_interval`` prints
a cadence the way every card shows it.
"""

import logging
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)
STATES = ("running", "paused", "off", "inactive")


def format_interval(seconds: int) -> str:
    """A cadence for people: ``600`` → "10 min", ``90`` → "90 s", ``3600`` → "1 h", ``5400`` → "1 h 30 min"."""
    seconds = int(seconds)
    minutes, rest = divmod(seconds, 60)
    if rest or not minutes:
        return f"{seconds} s"
    hours, minutes = divmod(minutes, 60)
    if not hours:
        return f"{minutes} min"
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


@dataclass(frozen=True)
class InboxReader:
    """One reader as the card shows it: its name, its state (one of ``STATES``), how often it lists the Inbox, and
    the admin page with its controls."""

    label: str
    state: str
    interval_seconds: int
    url: str = ""

    @property
    def every(self) -> str:
        return format_interval(self.interval_seconds)


_READERS: dict[str, str] = {}


def register_inbox_reader(name: str, *, describe: str) -> None:
    """Register an app's own Inbox scan: ``describe`` is the dotted path of a zero-argument callable returning an
    ``InboxReader``. Registering again is allowed only with the same path."""
    if not name or not describe:
        raise ImproperlyConfigured("An inbox reader needs a name and the dotted path of its description.")
    existing = _READERS.get(name)
    if existing is not None and existing != describe:
        raise ImproperlyConfigured(f"Inbox reader {name!r} is already registered differently.")
    _READERS[name] = describe


def registered_inbox_readers() -> dict[str, str]:
    return dict(_READERS)


def inbox_readers() -> list[InboxReader]:
    """Every registered reader's description, in registration order. One that cannot describe itself is left out
    (and logged), so a broken reader never breaks the Email Monitoring page."""
    found = []
    for name, path in _READERS.items():
        try:
            reader = import_string(path)()
        except Exception:  # noqa: BLE001 - one broken reader must never break the dashboard.
            logger.exception("Could not describe inbox reader %s", name)
            continue
        if isinstance(reader, InboxReader):
            found.append(reader)
        else:
            logger.error("Inbox reader %s described itself as %s, not an InboxReader", name, type(reader).__name__)
    return found

"""Shared fixtures for the helpdesk tests: a fake Graph reader (Microsoft Graph is never contacted), queue rows, and
running the ingest over them."""

import itertools
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.core.models import InboundMessage
from apps.core.services.email.telemetry import text
from apps.event.tests.helpers import make_admin, make_superuser

from ..models import HelpdeskSettings, Ticket
from ..services.ingest import runner
from .corpus import SITE

READER = "apps.helpdesk.services.ingest.runner.active_reader"
_graph_ids = itertools.count(1)


class FakeReader:
    """Stands in for ``GraphMailboxReader``: raw MIME by Graph id, or the exception to raise; records every read."""

    def __init__(self, bodies=None, *, mailbox=SITE, errors=None):
        self.mailbox = mailbox
        self.bodies = dict(bodies or {})
        self.errors = dict(errors or {})
        self.fetched = []

    def fetch_mime_head(self, graph_id, max_bytes):
        self.fetched.append((graph_id, max_bytes))
        if graph_id in self.errors:
            raise self.errors[graph_id]
        raw = self.bodies[graph_id]
        return raw[:max_bytes], len(raw) > max_bytes


def queue(raw: bytes | None = None, *, reader: FakeReader | None = None, received=None, conversation="", **values):
    """A pending inbound row for ``raw`` (registered with ``reader`` under a fresh Graph id)."""
    graph_id = values.pop("graph_id", None) or f"AAMk-{next(_graph_ids)}"
    if reader is not None and raw is not None:
        reader.bodies[graph_id] = raw
    message_id = values.pop("internet_message_id", None)
    if message_id is None and raw is not None:
        message_id = text.message_id(_header(raw, b"Message-ID"))
    return InboundMessage.objects.create(
        mailbox=values.pop("mailbox", SITE),
        graph_id=graph_id,
        received_at=received or timezone.now() - timedelta(minutes=5),
        internet_message_id=message_id or "",
        conversation_id=conversation,
        **values,
    )


def _header(raw: bytes, name: bytes) -> str:
    for line in raw.split(b"\r\n\r\n", 1)[0].splitlines():
        if line.lower().startswith(name.lower() + b":"):
            return line.split(b":", 1)[1].strip().decode()
    return ""


@contextmanager
def graph_reader(reader: FakeReader, problem: str = ""):
    with patch(READER, return_value=(reader, reader.mailbox if reader else SITE, problem)):
        yield reader


def ingest(reader: FakeReader, settings: HelpdeskSettings | None = None) -> runner.RunOutcome:
    with graph_reader(reader):
        return runner.run(settings or HelpdeskSettings.load())


def receive(raw: bytes, *, reader: FakeReader | None = None, **values) -> Ticket:
    """Queue one message, run the ingest, and return the ticket it landed on."""
    reader = reader or FakeReader()
    row = queue(raw, reader=reader, **values)
    ingest(reader)
    row.refresh_from_db()
    assert row.status == InboundMessage.Status.DONE, (row.status, row.last_error)
    return Ticket.objects.get(number=row.result["ticket"])


def helpdesk_staff(email="agent@example.com", **kwargs):
    return make_admin(apps=["helpdesk"], email=email, first_name="Avery", last_name="Agent", **kwargs)


__all__ = ["FakeReader", "graph_reader", "helpdesk_staff", "ingest", "make_admin", "make_superuser", "queue", "receive"]

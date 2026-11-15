"""``core.InboundMessage`` seen from the helpdesk: the Helpdesk → Ingest problems page.

A proxy (no table of its own), so the page belongs to the ``helpdesk`` app and its admin grant, not to ``core``'s.
"""

from apps.core.models import InboundMessage


class IngestRecord(InboundMessage):
    class Meta:
        proxy = True
        ordering = ["-received_at"]
        verbose_name = "Ingest Record"
        verbose_name_plural = "Ingest Problems"

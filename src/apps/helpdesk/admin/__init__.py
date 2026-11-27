"""Helpdesk admin: the ticket queue and ticket page, Ingest problems, Categories, SLA targets, Response templates and
Settings (every Admin). Assignment groups are deprecated and have no page (I2G-HELPDESK-01)."""

from .intake.problems import IngestRecordAdmin
from .intake.service_desk import ResponseTemplateAdmin, TicketCategoryAdmin
from .intake.settings import HelpdeskSettingsAdmin
from .intake.sla_targets import SLATargetAdmin
from .tickets.admin import TicketAdmin

__all__ = [
    "HelpdeskSettingsAdmin",
    "IngestRecordAdmin",
    "ResponseTemplateAdmin",
    "SLATargetAdmin",
    "TicketAdmin",
    "TicketCategoryAdmin",
]

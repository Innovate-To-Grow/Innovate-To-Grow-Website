"""Helpdesk admin: the ticket queue and ticket page, Ingest problems, Categories, Assignment groups, SLA targets,
Response templates and Settings (the Helpdesk grant)."""

from .intake.problems import IngestRecordAdmin
from .intake.settings import (
    AssignmentGroupAdmin,
    HelpdeskSettingsAdmin,
    ResponseTemplateAdmin,
    SLATargetAdmin,
    TicketCategoryAdmin,
)
from .tickets.admin import TicketAdmin

__all__ = [
    "AssignmentGroupAdmin",
    "HelpdeskSettingsAdmin",
    "IngestRecordAdmin",
    "ResponseTemplateAdmin",
    "SLATargetAdmin",
    "TicketAdmin",
    "TicketCategoryAdmin",
]

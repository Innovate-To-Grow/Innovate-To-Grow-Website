"""Helpdesk admin: the ticket queue and ticket page, Ingest problems, Categories, Assignment groups, SLA targets,
Response templates and Settings (the Helpdesk grant)."""

from .intake.problems import IngestRecordAdmin
from .intake.service_desk import AssignmentGroupAdmin, ResponseTemplateAdmin, SLATargetAdmin
from .intake.settings import HelpdeskSettingsAdmin, TicketCategoryAdmin
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

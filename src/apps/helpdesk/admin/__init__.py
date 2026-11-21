"""Helpdesk admin: the ticket queue and ticket page, Ingest problems, Categories, Assignment groups, SLA targets,
Response templates and Settings (the Helpdesk grant)."""

from .intake.problems import IngestRecordAdmin
from .intake.service_desk import AssignmentGroupAdmin, ResponseTemplateAdmin, TicketCategoryAdmin
from .intake.settings import HelpdeskSettingsAdmin
from .intake.sla_targets import SLATargetAdmin
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

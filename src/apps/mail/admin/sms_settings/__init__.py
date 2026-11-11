"""Mail → SMS Settings, SMS Opt-outs, SMS Links and Ticket SMS."""

from .config import SmsConfigAdmin
from .opt_outs import SmsOptOutAdmin
from .records import SmsLinkTokenAdmin, TicketSmsAdmin

__all__ = ["SmsConfigAdmin", "SmsLinkTokenAdmin", "SmsOptOutAdmin", "TicketSmsAdmin"]

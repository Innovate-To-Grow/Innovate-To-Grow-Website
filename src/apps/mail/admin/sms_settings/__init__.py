"""Mail → SMS Settings, SMS Opt-outs, SMS Links (and their revocations) and Ticket SMS."""

from .config import SmsConfigAdmin
from .opt_outs import SmsOptOutAdmin
from .records import SmsLinkRevocationAdmin, SmsLinkTokenAdmin, TicketSmsAdmin

__all__ = ["SmsConfigAdmin", "SmsLinkRevocationAdmin", "SmsLinkTokenAdmin", "SmsOptOutAdmin", "TicketSmsAdmin"]

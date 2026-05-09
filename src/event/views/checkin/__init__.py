import logging
import re

from event.models import CheckIn, CheckInRecord, EventRegistration

from .scan import CheckInScanView
from .status import CheckInStatusView
from .undo import CheckInUndoView

logger = logging.getLogger(__name__)
TICKET_CODE_RE = re.compile(r"\bI2G-[A-F0-9]{12}\b", re.IGNORECASE)

__all__ = [
    "CheckIn",
    "CheckInRecord",
    "CheckInScanView",
    "CheckInStatusView",
    "CheckInUndoView",
    "EventRegistration",
    "TICKET_CODE_RE",
    "logger",
]

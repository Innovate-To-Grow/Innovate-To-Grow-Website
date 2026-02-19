"""
Events app admin configuration.

Organized into modules by functionality:
- event: Event admin with inline editors
- schedule: Program and Track admin (event schedule)
- registration: Registration, ticket, and question admin
"""

from .event import EventAdmin
from .registration import (
    EventQuestionAdmin,
    EventRegistrationAdmin,
    EventRegistrationAnswerAdmin,
    EventTicketOptionAdmin,
)
from .schedule import ProgramAdmin, TrackAdmin

__all__ = [
    # Event
    "EventAdmin",
    # Schedule
    "ProgramAdmin",
    "TrackAdmin",
    # Registration
    "EventTicketOptionAdmin",
    "EventQuestionAdmin",
    "EventRegistrationAdmin",
    "EventRegistrationAnswerAdmin",
]

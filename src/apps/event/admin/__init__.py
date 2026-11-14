from .event import EventAdmin
from .registration import EventRegistrationAdmin
from .registration.checkin import CheckInAdmin, CheckInRecordAdmin
from .registration_sheet.sync_log import RegistrationSheetSyncLogAdmin
from .schedule.current_projects import CurrentProjectAdmin
from .schedule.project_schedule import CurrentProjectScheduleAdmin
from .schedule.sync_log import ScheduleSyncLogAdmin

__all__ = [
    "CheckInAdmin",
    "CheckInRecordAdmin",
    "CurrentProjectAdmin",
    "CurrentProjectScheduleAdmin",
    "EventAdmin",
    "EventRegistrationAdmin",
    "RegistrationSheetSyncLogAdmin",
    "ScheduleSyncLogAdmin",
]

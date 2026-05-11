import logging

from django.utils import timezone

from event.models import Event, EventRegistration, RegistrationSheetSyncLog

from .logs import record_sync_failure
from .rows import build_header, build_row
from .sheets import RegistrationSyncError

logger = logging.getLogger(__name__)


def sync_registrations_to_sheet(event: Event) -> int:
    if not event.registration_sheet_id:
        error_message = "Registration Google Sheet ID is not configured."
        record_sync_failure(event, error_message, sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        raise RegistrationSyncError(error_message)

    import event.services.registration_sheet_sync as sync_api

    credentials = sync_api.GoogleCredentialConfig.load()
    if not credentials.is_configured:
        error_message = "No active Google service account is configured."
        record_sync_failure(event, error_message, sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        raise RegistrationSyncError(error_message)

    registrations = list(EventRegistration.objects.filter(event=event).select_related("ticket").order_by("created_at"))
    question_texts = list(event.questions.order_by("order").values_list("text", flat=True))
    header = build_header(event, question_texts)
    rows = [
        build_row(registration, event, question_texts, index + 1) for index, registration in enumerate(registrations)
    ]

    try:
        worksheet = sync_api._get_worksheet(event)
        worksheet.clear()
        worksheet.update([header] + rows, value_input_option="USER_ENTERED")
        logger.info(
            "Full sync: %d registrations to sheet for event %s.",
            len(rows),
            event.slug,
        )
    except RegistrationSyncError as exc:
        record_sync_failure(event, str(exc), sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        raise
    except Exception as exc:
        record_sync_failure(event, str(exc), sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        raise RegistrationSyncError(f"Failed to write to Google Sheet: {exc}") from exc

    event.registration_sheet_synced_at = timezone.now()
    event.registration_sheet_sync_count = len(rows)
    event.registration_sheet_sync_error = ""
    event.save(
        update_fields=[
            "registration_sheet_synced_at",
            "registration_sheet_sync_count",
            "registration_sheet_sync_error",
            "updated_at",
        ]
    )
    RegistrationSheetSyncLog.objects.create(
        event=event,
        sync_type=RegistrationSheetSyncLog.SyncType.FULL,
        status=RegistrationSheetSyncLog.Status.SUCCESS,
        rows_written=len(rows),
    )
    return len(rows)

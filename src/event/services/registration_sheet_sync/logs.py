from django.utils import timezone

from event.models import Event, RegistrationSheetSyncLog


def record_sync_failure(
    event: Event,
    error_message: str,
    *,
    sync_type: str = "",
    update_synced_at: bool = False,
    rows_written: int | None = None,
) -> None:
    if update_synced_at:
        event.registration_sheet_synced_at = timezone.now()
    event.registration_sheet_sync_error = error_message
    event.save(
        update_fields=[
            *(["registration_sheet_synced_at"] if update_synced_at else []),
            "registration_sheet_sync_error",
            "updated_at",
        ]
    )
    if sync_type:
        log_kwargs = {
            "event": event,
            "sync_type": sync_type,
            "status": RegistrationSheetSyncLog.Status.FAILED,
            "error_message": error_message,
        }
        if rows_written is not None:
            log_kwargs["rows_written"] = rows_written
        RegistrationSheetSyncLog.objects.create(**log_kwargs)

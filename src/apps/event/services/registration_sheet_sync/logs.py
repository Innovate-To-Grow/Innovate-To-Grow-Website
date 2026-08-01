from apps.event.models import Event, RegistrationSheetSyncLog


def record_sync_failure(
    event: Event,
    error_message: str,
    *,
    sync_type: str = "",
    rows_written: int | None = None,
    cursor_from=None,
    cursor_to=None,
    selected_registration_ids: list[str] | None = None,
) -> None:
    event.registration_sheet_sync_error = error_message
    event.save(
        update_fields=[
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
            "cursor_from": cursor_from,
            "cursor_to": cursor_to,
            "selected_registration_ids": selected_registration_ids or [],
        }
        if rows_written is not None:
            log_kwargs["rows_written"] = rows_written
        RegistrationSheetSyncLog.objects.create(**log_kwargs)

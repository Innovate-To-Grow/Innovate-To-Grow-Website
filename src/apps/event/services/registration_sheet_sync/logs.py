from django.db.models import Q

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
    details: dict | None = None,
) -> None:
    events = Event.objects.filter(pk=event.pk)
    generation = (details or {}).get("generation")
    if generation is not None:
        events = events.filter(registration_sheet_sync_config__completed_generation__lt=generation)
    if cursor_to is not None:
        events = events.filter(
            Q(registration_sheet_synced_at__isnull=True) | Q(registration_sheet_synced_at__lte=cursor_to)
        )
    events.update(registration_sheet_sync_error=error_message)
    if sync_type:
        log_kwargs = {
            "event": event,
            "sync_type": sync_type,
            "status": RegistrationSheetSyncLog.Status.FAILED,
            "error_message": error_message,
            "cursor_from": cursor_from,
            "cursor_to": cursor_to,
            "selected_registration_ids": selected_registration_ids or [],
            "details": details or {},
        }
        if rows_written is not None:
            log_kwargs["rows_written"] = rows_written
        RegistrationSheetSyncLog.objects.create(**log_kwargs)

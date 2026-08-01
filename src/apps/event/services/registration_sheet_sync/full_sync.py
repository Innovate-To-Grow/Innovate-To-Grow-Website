import logging

from django.db import transaction
from django.utils import timezone

from apps.event.models import Event, EventRegistration, RegistrationSheetSyncLog

from .logs import record_sync_failure
from .rows import build_header, build_row
from .sheets import (
    RegistrationSyncError,
    backup_legacy_sheet_if_needed,
    ensure_registration_id_protected,
    read_sheet_values,
    service_account_email,
)

logger = logging.getLogger(__name__)


def sync_registrations_to_sheet(event: Event) -> int:
    if not event.registration_sheet_id:
        error_message = "Registration Google Sheet ID is not configured."
        record_sync_failure(event, error_message, sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        raise RegistrationSyncError(error_message)

    import apps.event.services.registration_sheet_sync as sync_api

    credentials = sync_api.GoogleCredentialConfig.load()
    if not credentials.is_configured:
        error_message = "No active Google service account is configured."
        record_sync_failure(event, error_message, sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        raise RegistrationSyncError(error_message)

    cursor_from = event.registration_sheet_synced_at
    cursor_to = timezone.now()
    selected_ids: list[str] = []
    try:
        with transaction.atomic():
            event = Event.objects.select_for_update(no_key=True).get(pk=event.pk)
            cursor_from = event.registration_sheet_synced_at
            cursor_to = timezone.now()
            registrations = list(
                EventRegistration.objects.filter(event=event, created_at__lte=cursor_to)
                .select_related("ticket")
                .order_by("created_at", "pk")
            )
            selected_ids = [str(registration.pk) for registration in registrations]
            question_texts = list(event.questions.order_by("order").values_list("text", flat=True))
            header = build_header(event, question_texts)
            rows = [
                build_row(registration, event, question_texts, index + 1)
                for index, registration in enumerate(registrations)
            ]

            worksheet = sync_api._get_worksheet(event)
            existing_values = read_sheet_values(worksheet)
            backup_legacy_sheet_if_needed(
                worksheet,
                existing_values,
                expected_header=header,
            )
            worksheet.clear()
            worksheet.update([header] + rows, value_input_option="USER_ENTERED")
            ensure_registration_id_protected(
                worksheet,
                header,
                editor_email=service_account_email(credentials),
            )
            logger.info(
                "Full sync: %d registrations to sheet for event %s.",
                len(rows),
                event.slug,
            )

            Event.objects.filter(pk=event.pk).update(
                registration_sheet_synced_at=cursor_to,
                registration_sheet_sync_count=len(rows),
                registration_sheet_sync_error="",
                updated_at=timezone.now(),
            )
            RegistrationSheetSyncLog.objects.create(
                event=event,
                sync_type=RegistrationSheetSyncLog.SyncType.FULL,
                status=RegistrationSheetSyncLog.Status.SUCCESS,
                rows_written=len(rows),
                cursor_from=cursor_from,
                cursor_to=cursor_to,
                selected_registration_ids=selected_ids,
            )
            return len(rows)
    except RegistrationSyncError as exc:
        record_sync_failure(
            Event.objects.get(pk=event.pk),
            str(exc),
            sync_type=RegistrationSheetSyncLog.SyncType.FULL,
            rows_written=0,
            cursor_from=cursor_from,
            cursor_to=cursor_to,
            selected_registration_ids=selected_ids,
        )
        raise
    except Exception as exc:
        record_sync_failure(
            Event.objects.get(pk=event.pk),
            str(exc),
            sync_type=RegistrationSheetSyncLog.SyncType.FULL,
            rows_written=0,
            cursor_from=cursor_from,
            cursor_to=cursor_to,
            selected_registration_ids=selected_ids,
        )
        raise RegistrationSyncError(f"Failed to write to Google Sheet: {exc}") from exc

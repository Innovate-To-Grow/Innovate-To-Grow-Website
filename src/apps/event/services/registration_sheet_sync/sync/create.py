"""Moving an event's registrations to a fresh worksheet in the same spreadsheet."""

from datetime import UTC, datetime

from django.db import transaction
from django.utils import timezone

from apps.event.models import (
    Event,
    RegistrationSheetSyncConfig,
    RegistrationSheetSyncLog,
)

from ..schedule.state import begin_sync, complete_sync
from ..worksheet.sheets import RegistrationSyncConflict, RegistrationSyncError
from ..worksheet.snapshot import backup_worksheet, read_snapshot, spreadsheet_for
from .engine import _record_success, _write_plan
from .prepare import _config_for, _prepare, _verify_plan
from .run_failures import _record_failed_run, _rows_written, _RunState


def _add_fresh_worksheet(worksheet, old_plan, config):
    return spreadsheet_for(worksheet).add_worksheet(
        title=f"Registrations {datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f')}",
        rows=max(100, len(old_plan.active_ids) + config.header_row),
        cols=max(26, len(old_plan.columns)),
    )


def _create_locked(run: _RunState, *, expected_fingerprint, generation, started_at):
    with transaction.atomic():
        event = run.event = Event.objects.select_for_update(no_key=True).get(pk=run.event.pk)
        config = _config_for(event)
        worksheet, snapshot, old_plan, credentials = _prepare(event, config, lock=True)
        if expected_fingerprint is None or old_plan.fingerprint != expected_fingerprint:
            raise RegistrationSyncConflict("Creating a new worksheet requires a current reviewed preview.")
        if read_snapshot(worksheet).fingerprint() != snapshot.fingerprint():
            raise RegistrationSyncConflict("The worksheet changed. Preview again before creating a new worksheet.")
        run.backup = backup_worksheet(worksheet)
        new_worksheet = run.new_worksheet = _add_fresh_worksheet(worksheet, old_plan, config)
        config.column_mappings = {}
        _, new_snapshot, run.plan, _ = _prepare(event, config, worksheet=new_worksheet, lock=True)
        _verify_plan(run.plan)
        _write_plan(new_worksheet, new_snapshot, run.plan, event=event, config=config, credentials=credentials)
        run.provider_write_completed = True
        Event.objects.filter(pk=event.pk).update(registration_sheet_gid=new_worksheet.id)
        RegistrationSheetSyncConfig.objects.filter(pk=config.pk).update(column_mappings={})
        _record_success(
            event,
            run.plan,
            new_snapshot,
            generation=generation,
            sync_type=RegistrationSheetSyncLog.SyncType.FULL,
            cursor_from=event.registration_sheet_synced_at,
            started_at=started_at,
        )
    return new_worksheet.id


def create_registration_worksheet(event, *, expected_fingerprint=None):
    """Back up and preserve the old worksheet; select a fresh populated export only on success."""
    state = begin_sync(event.pk)
    generation = state["captured_generation"]
    started_at = timezone.now()
    run = _RunState(event=event)
    try:
        worksheet_id = _create_locked(
            run, expected_fingerprint=expected_fingerprint, generation=generation, started_at=started_at
        )
        complete_sync(event.pk, generation, **run.plan.counts)
        return worksheet_id
    except Exception as exc:
        _record_failed_run(
            run.event,
            exc,
            generation=generation,
            sync_type=RegistrationSheetSyncLog.SyncType.FULL,
            started_at=started_at,
            rows_written=_rows_written(run.plan, run.provider_write_completed),
            details={
                "worksheet_gid": run.event.registration_sheet_gid,
                "backup_worksheet_gid": run.backup.id if run.backup else None,
                "created_worksheet_gid": run.new_worksheet.id if run.new_worksheet else None,
                "provider_write_completed": run.provider_write_completed,
                **(run.plan.counts if run.plan else {}),
            },
        )
        if isinstance(exc, RegistrationSyncError):
            raise
        raise RegistrationSyncError(f"Failed to create registration worksheet: {exc}") from exc

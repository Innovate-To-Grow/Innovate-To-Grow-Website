import logging

from .client import GoogleSheetsConfigError, fetch_raw_values, normalize_values
from .sync_helpers import (
    build_header_index,
    build_push_rows,
    build_sync_stats,
    create_sync_log,
    determine_pull_status,
    determine_push_status,
    get_transform_hook,
    process_pull_rows,
)

logger = logging.getLogger(__name__)


def pull_from_sheet(sheet_link, triggered_by=None):
    """
    Pull data from a Google Sheet into the Django database.

    Fetches sheet data, maps columns to model fields using column_mapping,
    resolves FK fields via __ syntax and fk_config, and upserts rows via
    update_or_create().

    Returns a SyncLog instance with stats.
    """
    from django.utils import timezone

    from sheets.models import SyncLog

    started_at = timezone.now()
    stats = build_sync_stats()
    error_details = []

    try:
        # 1. Fetch + normalize sheet data
        range_ref = sheet_link.get_sheet_range()
        if not range_ref:
            raise GoogleSheetsConfigError(f"SheetLink '{sheet_link.name}' has no sheet_name or range_a1.")

        raw_values = fetch_raw_values(sheet_link.account, sheet_link.spreadsheet_id, range_ref)
        headers, rows = normalize_values(raw_values)

        if not headers or not rows:
            return create_sync_log(
                SyncLog,
                sheet_link=sheet_link,
                direction=SyncLog.Direction.PULL,
                status=SyncLog.Status.SUCCESS,
                started_at=started_at,
                triggered_by=triggered_by,
                error_details=error_details,
                stats=stats,
            )

        header_index = {h: i for i, h in enumerate(headers)}
        column_mapping = sheet_link.column_mapping or {}
        header_index = build_header_index(headers, column_mapping)
        model_class = sheet_link.get_model_class()
        lookup_fields = sheet_link.lookup_fields or []
        fk_config = sheet_link.fk_config or {}
        transform_hook = get_transform_hook(sheet_link)
        process_pull_rows(
            rows=rows,
            header_index=header_index,
            column_mapping=column_mapping,
            model_class=model_class,
            lookup_fields=lookup_fields,
            fk_config=fk_config,
            transform_hook=transform_hook,
            sheet_link=sheet_link,
            stats=stats,
            error_details=error_details,
            logger=logger,
        )

        status = determine_pull_status(SyncLog, stats)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Pull failed for '%s'", sheet_link.name)
        error_details.append({"row": 0, "error": str(exc)})
        status = SyncLog.Status.FAILED

    return create_sync_log(
        SyncLog,
        sheet_link=sheet_link,
        direction=SyncLog.Direction.PULL,
        status=status,
        started_at=started_at,
        triggered_by=triggered_by,
        error_details=error_details,
        stats=stats,
    )


def push_to_sheet(sheet_link, queryset=None, triggered_by=None):
    """
    Push data from the Django database to a Google Sheet.

    Queries the linked model, serializes field values to rows using
    column_mapping, clears the sheet range, and writes header + data rows.

    Returns a SyncLog instance with stats.
    """
    from django.utils import timezone

    from sheets.models import SyncLog

    from .client import clear_range, write_values

    started_at = timezone.now()
    stats = build_sync_stats()
    error_details = []

    try:
        model_class = sheet_link.get_model_class()
        column_mapping = sheet_link.column_mapping or {}

        if not column_mapping:
            raise GoogleSheetsConfigError(f"SheetLink '{sheet_link.name}' has no column_mapping.")

        range_ref = sheet_link.get_sheet_range()
        if not range_ref:
            raise GoogleSheetsConfigError(f"SheetLink '{sheet_link.name}' has no sheet_name or range_a1.")

        # Default queryset: all non-deleted objects
        if queryset is None:
            queryset = model_class.objects.all()

        all_rows = build_push_rows(
            queryset=queryset,
            column_mapping=column_mapping,
            stats=stats,
            error_details=error_details,
            sheet_link=sheet_link,
            logger=logger,
        )
        clear_range(sheet_link.account, sheet_link.spreadsheet_id, range_ref)
        write_values(sheet_link.account, sheet_link.spreadsheet_id, range_ref, all_rows)

        status = determine_push_status(SyncLog, stats)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Push failed for '%s'", sheet_link.name)
        error_details.append({"row": 0, "error": str(exc)})
        status = SyncLog.Status.FAILED

    return create_sync_log(
        SyncLog,
        sheet_link=sheet_link,
        direction=SyncLog.Direction.PUSH,
        status=status,
        started_at=started_at,
        triggered_by=triggered_by,
        error_details=error_details,
        stats=stats,
    )

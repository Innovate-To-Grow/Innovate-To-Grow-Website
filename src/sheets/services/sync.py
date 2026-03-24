"""
Core sync engine for bi-directional Google Sheets <-> Django model sync.

pull_from_sheet: Sheet → DB (fetch rows, map columns, upsert into model)
push_to_sheet:   DB → Sheet (query model, serialize fields, write to sheet)
"""

import importlib
import logging

from django.utils import timezone

from .client import GoogleSheetsConfigError, fetch_raw_values, normalize_values
from .field_resolver import coerce_field_value, group_fk_columns, resolve_fk, serialize_field_value

logger = logging.getLogger(__name__)


def _import_hook(dotted_path: str):
    """Import a function from a dotted path like 'projects.services.hooks.resolve_project_row'."""
    module_path, func_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def pull_from_sheet(sheet_link, triggered_by=None):
    """
    Pull data from a Google Sheet into the Django database.

    Fetches sheet data, maps columns to model fields using column_mapping,
    resolves FK fields via __ syntax and fk_config, and upserts rows via
    update_or_create().

    Returns a SyncLog instance with stats.
    """
    from sheets.models import SyncLog

    started_at = timezone.now()
    stats = {
        "rows_processed": 0,
        "rows_created": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "rows_failed": 0,
    }
    error_details = []

    try:
        # 1. Fetch + normalize sheet data
        range_ref = sheet_link.get_sheet_range()
        if not range_ref:
            raise GoogleSheetsConfigError(f"SheetLink '{sheet_link.name}' has no sheet_name or range_a1.")

        raw_values = fetch_raw_values(sheet_link.account, sheet_link.spreadsheet_id, range_ref)
        headers, rows = normalize_values(raw_values)

        if not headers or not rows:
            return SyncLog.objects.create(
                sheet_link=sheet_link,
                direction=SyncLog.Direction.PULL,
                status=SyncLog.Status.SUCCESS,
                started_at=started_at,
                completed_at=timezone.now(),
                triggered_by=triggered_by,
                **stats,
            )

        # 2. Build column index: {sheet_header: column_index}
        header_index = {h: i for i, h in enumerate(headers)}

        # 3. Validate mapped headers exist
        column_mapping = sheet_link.column_mapping or {}
        for sheet_header, _field_path in column_mapping.items():
            if sheet_header not in header_index:
                raise GoogleSheetsConfigError(
                    f"Mapped header '{sheet_header}' not found in sheet. Available: {headers}"
                )

        # 4. Group FK columns and direct mappings
        fk_groups, direct_mappings = group_fk_columns(column_mapping)

        # 5. Get model class and optional transform hook
        model_class = sheet_link.get_model_class()
        lookup_fields = sheet_link.lookup_fields or []
        fk_config = sheet_link.fk_config or {}

        transform_hook = None
        if sheet_link.row_transform_hook:
            transform_hook = _import_hook(sheet_link.row_transform_hook)

        # 6. Process each row
        for row_idx, row in enumerate(rows, start=2):  # row 1 is headers
            stats["rows_processed"] += 1

            try:
                # Build raw row dict: {sheet_header: cell_value}
                # Include __skip__ columns so transform hooks can access them
                raw_row = {h: row[header_index[h]] for h in column_mapping if h in header_index}

                # Apply transform hook if configured
                if transform_hook:
                    raw_row = transform_hook(raw_row, sheet_link)
                    if raw_row is None:
                        stats["rows_skipped"] += 1
                        continue

                # Resolve direct fields
                field_values = {}
                for sheet_header, field_name in direct_mappings.items():
                    raw_value = raw_row.get(sheet_header, "")
                    try:
                        model_field = model_class._meta.get_field(field_name)
                        field_values[field_name] = coerce_field_value(model_field, raw_value)
                    except Exception:  # noqa: BLE001
                        field_values[field_name] = raw_value

                # Pick up any values injected by the transform hook (non-string = resolved instances)
                for key, value in raw_row.items():
                    if not isinstance(value, str) and key not in field_values:
                        field_values[key] = value

                # Resolve FK fields from __ groups
                for fk_field_name, related_fields in fk_groups.items():
                    # Skip if the transform hook already set this FK
                    if fk_field_name in field_values:
                        continue

                    fk_lookup = {}
                    for related_field_name, sheet_header in related_fields.items():
                        fk_lookup[related_field_name] = raw_row.get(sheet_header, "")

                    field_values[fk_field_name] = resolve_fk(model_class, fk_field_name, fk_lookup, fk_config)

                # Skip rows where all lookup fields are empty
                if lookup_fields:
                    lookup_vals = [field_values.get(f) for f in lookup_fields]
                    if all(v is None or v == "" for v in lookup_vals):
                        stats["rows_skipped"] += 1
                        continue

                # Split into lookup_kwargs and defaults
                lookup_kwargs = {f: field_values[f] for f in lookup_fields if f in field_values}
                defaults = {f: v for f, v in field_values.items() if f not in lookup_fields}

                # Upsert
                _, created = model_class.objects.update_or_create(**lookup_kwargs, defaults=defaults)
                if created:
                    stats["rows_created"] += 1
                else:
                    stats["rows_updated"] += 1

            except Exception as exc:  # noqa: BLE001
                stats["rows_failed"] += 1
                error_details.append({"row": row_idx, "error": str(exc)})
                logger.warning("Pull row %d failed for '%s': %s", row_idx, sheet_link.name, exc)

        # Determine status
        if stats["rows_failed"] == 0:
            status = SyncLog.Status.SUCCESS
        elif stats["rows_created"] + stats["rows_updated"] > 0:
            status = SyncLog.Status.PARTIAL
        else:
            status = SyncLog.Status.FAILED

    except Exception as exc:  # noqa: BLE001
        logger.exception("Pull failed for '%s'", sheet_link.name)
        error_details.append({"row": 0, "error": str(exc)})
        status = SyncLog.Status.FAILED

    return SyncLog.objects.create(
        sheet_link=sheet_link,
        direction=SyncLog.Direction.PULL,
        status=status,
        started_at=started_at,
        completed_at=timezone.now(),
        triggered_by=triggered_by,
        error_details=error_details,
        **stats,
    )


def push_to_sheet(sheet_link, queryset=None, triggered_by=None):
    """
    Push data from the Django database to a Google Sheet.

    Queries the linked model, serializes field values to rows using
    column_mapping, clears the sheet range, and writes header + data rows.

    Returns a SyncLog instance with stats.
    """
    from sheets.models import SyncLog

    from .client import clear_range, write_values

    started_at = timezone.now()
    stats = {
        "rows_processed": 0,
        "rows_created": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "rows_failed": 0,
    }
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

        # Build header row (sheet headers in mapping order)
        sheet_headers = [h for h, fp in column_mapping.items() if fp != "__skip__"]
        field_paths = [column_mapping[h] for h in sheet_headers]

        # Build data rows
        all_rows = [sheet_headers]  # header row first
        for obj in queryset:
            stats["rows_processed"] += 1
            try:
                row = []
                for field_path in field_paths:
                    row.append(serialize_field_value(obj, field_path))
                all_rows.append(row)
                stats["rows_created"] += 1  # "created" in sheet context = row written
            except Exception as exc:  # noqa: BLE001
                stats["rows_failed"] += 1
                error_details.append({"row": stats["rows_processed"] + 1, "error": str(exc)})
                logger.warning("Push row failed for '%s': %s", sheet_link.name, exc)

        # Clear existing data and write new
        clear_range(sheet_link.account, sheet_link.spreadsheet_id, range_ref)
        write_values(sheet_link.account, sheet_link.spreadsheet_id, range_ref, all_rows)

        if stats["rows_failed"] == 0:
            status = SyncLog.Status.SUCCESS
        elif stats["rows_created"] > 0:
            status = SyncLog.Status.PARTIAL
        else:
            status = SyncLog.Status.FAILED

    except Exception as exc:  # noqa: BLE001
        logger.exception("Push failed for '%s'", sheet_link.name)
        error_details.append({"row": 0, "error": str(exc)})
        status = SyncLog.Status.FAILED

    return SyncLog.objects.create(
        sheet_link=sheet_link,
        direction=SyncLog.Direction.PUSH,
        status=status,
        started_at=started_at,
        completed_at=timezone.now(),
        triggered_by=triggered_by,
        error_details=error_details,
        **stats,
    )

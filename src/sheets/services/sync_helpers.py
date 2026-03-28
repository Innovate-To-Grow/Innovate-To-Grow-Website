import importlib

from django.utils import timezone

from .client import GoogleSheetsConfigError
from .field_resolver import coerce_field_value, group_fk_columns, resolve_fk, serialize_field_value


def import_hook(dotted_path: str):
    module_path, func_name = dotted_path.rsplit(".", 1)
    return getattr(importlib.import_module(module_path), func_name)


def build_sync_stats():
    return {
        "rows_processed": 0,
        "rows_created": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "rows_failed": 0,
    }


def determine_pull_status(sync_log_model, stats):
    if stats["rows_failed"] == 0:
        return sync_log_model.Status.SUCCESS
    if stats["rows_created"] + stats["rows_updated"] > 0:
        return sync_log_model.Status.PARTIAL
    return sync_log_model.Status.FAILED


def determine_push_status(sync_log_model, stats):
    if stats["rows_failed"] == 0:
        return sync_log_model.Status.SUCCESS
    if stats["rows_created"] > 0:
        return sync_log_model.Status.PARTIAL
    return sync_log_model.Status.FAILED


def create_sync_log(sync_log_model, *, sheet_link, direction, status, started_at, triggered_by, error_details, stats):
    return sync_log_model.objects.create(
        sheet_link=sheet_link,
        direction=direction,
        status=status,
        started_at=started_at,
        completed_at=timezone.now(),
        triggered_by=triggered_by,
        error_details=error_details,
        **stats,
    )


def build_header_index(headers, column_mapping):
    header_index = {header: index for index, header in enumerate(headers)}
    for sheet_header in column_mapping:
        if sheet_header not in header_index:
            raise GoogleSheetsConfigError(f"Mapped header '{sheet_header}' not found in sheet. Available: {headers}")
    return header_index


def get_transform_hook(sheet_link):
    if not sheet_link.row_transform_hook:
        return None
    return import_hook(sheet_link.row_transform_hook)


def process_pull_rows(
    *,
    rows,
    header_index,
    column_mapping,
    model_class,
    lookup_fields,
    fk_config,
    transform_hook,
    sheet_link,
    stats,
    error_details,
    logger,
):
    fk_groups, direct_mappings = group_fk_columns(column_mapping)

    for row_idx, row in enumerate(rows, start=2):
        stats["rows_processed"] += 1
        try:
            field_values = build_pull_field_values(
                row=row,
                header_index=header_index,
                column_mapping=column_mapping,
                direct_mappings=direct_mappings,
                fk_groups=fk_groups,
                model_class=model_class,
                fk_config=fk_config,
                transform_hook=transform_hook,
                sheet_link=sheet_link,
            )
            if should_skip_pull_row(field_values, lookup_fields):
                stats["rows_skipped"] += 1
                continue

            lookup_kwargs = {field: field_values[field] for field in lookup_fields if field in field_values}
            defaults = {field: value for field, value in field_values.items() if field not in lookup_fields}
            _, created = model_class.objects.update_or_create(**lookup_kwargs, defaults=defaults)
            stats["rows_created" if created else "rows_updated"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["rows_failed"] += 1
            error_details.append({"row": row_idx, "error": str(exc)})
            logger.warning("Pull row %d failed for '%s': %s", row_idx, sheet_link.name, exc)


def build_push_rows(*, queryset, column_mapping, stats, error_details, sheet_link, logger):
    sheet_headers = [header for header, field_path in column_mapping.items() if field_path != "__skip__"]
    field_paths = [column_mapping[header] for header in sheet_headers]
    all_rows = [sheet_headers]

    for obj in queryset:
        stats["rows_processed"] += 1
        try:
            row = [serialize_field_value(obj, field_path) for field_path in field_paths]
            all_rows.append(row)
            stats["rows_created"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["rows_failed"] += 1
            error_details.append({"row": stats["rows_processed"] + 1, "error": str(exc)})
            logger.warning("Push row failed for '%s': %s", sheet_link.name, exc)

    return all_rows


def build_pull_field_values(
    *,
    row,
    header_index,
    column_mapping,
    direct_mappings,
    fk_groups,
    model_class,
    fk_config,
    transform_hook,
    sheet_link,
):
    raw_row = {header: row[header_index[header]] for header in column_mapping if header in header_index}
    if transform_hook:
        raw_row = transform_hook(raw_row, sheet_link)
        if raw_row is None:
            return {}

    field_values = build_direct_field_values(raw_row, direct_mappings, model_class)
    for key, value in raw_row.items():
        if not isinstance(value, str) and key not in field_values:
            field_values[key] = value

    for fk_field_name, related_fields in fk_groups.items():
        if fk_field_name in field_values:
            continue
        fk_lookup = {
            related_field_name: raw_row.get(sheet_header, "")
            for related_field_name, sheet_header in related_fields.items()
        }
        field_values[fk_field_name] = resolve_fk(model_class, fk_field_name, fk_lookup, fk_config)

    return field_values


def build_direct_field_values(raw_row, direct_mappings, model_class):
    field_values = {}
    for sheet_header, field_name in direct_mappings.items():
        raw_value = raw_row.get(sheet_header, "")
        try:
            model_field = model_class._meta.get_field(field_name)
            field_values[field_name] = coerce_field_value(model_field, raw_value)
        except Exception:  # noqa: BLE001
            field_values[field_name] = raw_value
    return field_values


def should_skip_pull_row(field_values, lookup_fields):
    if field_values == {}:
        return True
    if not lookup_fields:
        return False
    lookup_values = [field_values.get(field) for field in lookup_fields]
    return all(value is None or value == "" for value in lookup_values)

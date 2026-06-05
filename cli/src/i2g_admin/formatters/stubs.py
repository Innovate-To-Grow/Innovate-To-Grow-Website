"""Wave-2 output formatters: ``text`` / ``yaml`` / ``csv`` (the U2 seam).

U1 registers the names so ``--output text|yaml|csv`` is a recognized choice; U2
fills in the real bodies here WITHOUT touching ``formatters/__init__.py``.

- ``yaml``: ``yaml.safe_dump`` with stable key order, after a JSON round-trip so
  UUIDs / datetimes / Decimals serialize as plain strings.
- ``csv``: stdlib ``csv`` + ``io.StringIO``. List of dicts → header (union of
  keys, first-seen order) + one row each; single dict → ``key,value`` rows; list
  of scalars → one value per line.
- ``text``: AWS-CLI-style flattened, TAB-separated, no header. List of dicts →
  one tab-joined line of values per row; single dict → one tab-joined line;
  list of scalars → one per line; scalar → ``str``.
"""

import csv
import io
import json
from typing import Any

import yaml

from . import register


def _json_safe(data: Any) -> Any:
    """Normalize non-JSON-native values (UUID/datetime/Decimal) to plain types."""
    return json.loads(json.dumps(data, default=str))


def _cell(value: Any) -> str:
    """Render a single field value as a string (None → empty, like AWS CLI)."""
    if value is None:
        return ""
    return str(value)


@register("text")
def _format_text(data: Any) -> str:
    if isinstance(data, list):
        lines = []
        for row in data:
            if isinstance(row, dict):
                lines.append("\t".join(_cell(value) for value in row.values()))
            else:
                lines.append(_cell(row))
        return "\n".join(lines)
    if isinstance(data, dict):
        return "\t".join(_cell(value) for value in data.values())
    return _cell(data)


@register("yaml")
def _format_yaml(data: Any) -> str:
    return yaml.safe_dump(_json_safe(data), sort_keys=True, default_flow_style=False)


@register("csv")
def _format_csv(data: Any) -> str:
    buffer = io.StringIO()
    if isinstance(data, list):
        if data and all(isinstance(row, dict) for row in data):
            columns: list[str] = []
            for row in data:
                for key in row:
                    if key not in columns:
                        columns.append(key)
            writer = csv.writer(buffer)
            writer.writerow(columns)
            for row in data:
                writer.writerow([_cell(row.get(column)) for column in columns])
        else:
            writer = csv.writer(buffer)
            for row in data:
                writer.writerow([_cell(row)])
    elif isinstance(data, dict):
        writer = csv.writer(buffer)
        writer.writerow(["key", "value"])
        for key, value in data.items():
            writer.writerow([_cell(key), _cell(value)])
    else:
        writer = csv.writer(buffer)
        writer.writerow([_cell(data)])
    return buffer.getvalue()

"""How the ``StyleSheet`` rows of a database differ from the repo seed.

The seed is ``migrations/data/stylesheets.json``, the Django fixture that migration
0004 loads and later migrations re-sync from. Sheets are compared on *normalised* CSS
(CRLF to LF, trailing whitespace stripped), so a textarea save that only changed line
endings is not reported as an edit.

Migration 0026 switched off the component sheets (``RETIRED_SHEETS``): the frontend bundle
ships their CSS, so for them "off" is the expected state, whatever the seed says.
"""

import difflib
import hashlib
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from django.utils import timezone

from apps.cms.models import CMSPage, StyleSheet

SEED_PATH = Path(__file__).resolve().parents[2] / "migrations" / "data" / "stylesheets.json"
BACKUP_SUFFIXES = ("-pre-redesign", "-pre-audit-fixes")
# Kept equal to RETIRED_SHEETS in migration 0026 (a test checks it).
RETIRED_SHEETS = frozenset(
    {
        "layout-container",
        "layout-menu",
        "layout-footer",
        "auth",
        "page-news",
        "page-projects",
        "page-events",
        "page-subscribe",
        "page-misc",
        "maintenance",
    }
)

STATUS_IN_SYNC = "in_sync"
STATUS_EDITED = "edited"
STATUS_SETTINGS_CHANGED = "settings_changed"
STATUS_UNMANAGED = "unmanaged"
STATUS_BACKUP_COPY = "backup_copy"
STATUS_RETIRED = "retired"
STATUS_UNKNOWN = "unknown"
STATUS_LABELS = {
    STATUS_IN_SYNC: "In sync with the repo seed",
    STATUS_EDITED: "Edited (CSS differs from the repo seed)",
    STATUS_SETTINGS_CHANGED: "Active / order differ from the repo seed",
    STATUS_UNMANAGED: "Unmanaged (not in the repo seed)",
    STATUS_BACKUP_COPY: "Inactive backup copy left by a migration",
    STATUS_RETIRED: "Retired (the frontend bundle ships this CSS)",
    STATUS_UNKNOWN: "Unknown (repo seed file not found)",
}
# Fields the re-sync migrations overwrite besides the CSS itself.
SEED_SETTINGS_FIELDS = ("is_active", "sort_order")


def normalize_css(css) -> str:
    """CSS with LF line endings, no trailing whitespace and one trailing newline."""
    text = (css or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + ("\n" if lines else "")


def css_checksum(css) -> str:
    return hashlib.sha256(normalize_css(css).encode("utf-8")).hexdigest()


@lru_cache(maxsize=8)
def _read_seed(path: str, mtime_ns: int) -> tuple[tuple[str, str], ...]:
    with open(path, encoding="utf-8") as handle:
        records = json.load(handle)
    return tuple((record["fields"]["name"], json.dumps(record["fields"])) for record in records)


def load_seed_sheets(path=None) -> dict[str, dict]:
    """The seed sheets by name (``{}`` when the seed file is missing); safe to mutate."""
    seed_path = Path(path or SEED_PATH)
    if not seed_path.exists():
        return {}
    cached = _read_seed(str(seed_path), seed_path.stat().st_mtime_ns)
    return {name: json.loads(fields) for name, fields in cached}


def is_backup_copy(name: str) -> bool:
    return name.endswith(BACKUP_SUFFIXES)


def changed_settings(sheet, seed: dict | None) -> list[str]:
    """The seed-managed fields other than ``css`` whose database value differs from the seed.

    A retired sheet is expected to be off, and its order no longer matters while it is.
    """
    if seed is None:
        return []
    if sheet.name in RETIRED_SHEETS:
        return ["is_active"] if sheet.is_active else []
    return [field for field in SEED_SETTINGS_FIELDS if field in seed and getattr(sheet, field) != seed[field]]


def sheet_status(sheet, seeds: dict[str, dict]) -> str:
    seed = seeds.get(sheet.name)
    if seed is not None and sheet.name in RETIRED_SHEETS:
        # Switched back on, it is served again in front of the bundle's copy.
        return STATUS_SETTINGS_CHANGED if sheet.is_active else STATUS_RETIRED
    if seed is None:
        # A backup copy an admin re-activated (the documented way to switch back) is served
        # CSS the seed does not hold, so it counts as unmanaged.
        if is_backup_copy(sheet.name) and not sheet.is_active:
            return STATUS_BACKUP_COPY
        return STATUS_UNMANAGED
    if css_checksum(sheet.css) != css_checksum(seed.get("css", "")):
        return STATUS_EDITED
    if changed_settings(sheet, seed):
        return STATUS_SETTINGS_CHANGED
    return STATUS_IN_SYNC


def seed_status_label(sheet, seed_path=None) -> str:
    """The admin's label for ``sheet``; ``unknown`` when the seed file cannot be read."""
    seeds = load_seed_sheets(seed_path)
    if not seeds:
        return STATUS_LABELS[STATUS_UNKNOWN]
    return STATUS_LABELS[sheet_status(sheet, seeds)]


def sheet_diff(sheet, seed_css) -> str:
    """Unified diff from the seed CSS to the database CSS of one sheet."""
    seed_lines = normalize_css(seed_css).splitlines(keepends=True)
    db_lines = normalize_css(sheet.css).splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            seed_lines,
            db_lines,
            fromfile=f"seed/{sheet.name}.css",
            tofile=f"database/{sheet.name}.css",
        )
    )


def _count_changes(diff: str) -> tuple[int, int]:
    """Added and removed lines of a unified diff; the ``---``/``+++`` file header precedes the first hunk."""
    added = removed = 0
    in_hunks = False
    for line in diff.splitlines():
        if line.startswith("@@"):
            in_hunks = True
        elif in_hunks and line.startswith("+"):
            added += 1
        elif in_hunks and line.startswith("-"):
            removed += 1
    return added, removed


def describe_sheet(sheet, seeds: dict[str, dict]) -> dict:
    status = sheet_status(sheet, seeds)
    entry = {
        "name": sheet.name,
        "display_name": sheet.display_name,
        "is_active": sheet.is_active,
        "sort_order": sheet.sort_order,
        "status": status,
        "changed_settings": changed_settings(sheet, seeds.get(sheet.name)),
        "added_lines": 0,
        "removed_lines": 0,
        "diff": "",
    }
    if status == STATUS_EDITED:
        diff = sheet_diff(sheet, seeds[sheet.name].get("css", ""))
        entry["diff"] = diff
        entry["added_lines"], entry["removed_lines"] = _count_changes(diff)
    return entry


def pages_with_css() -> list[dict]:
    """CMS pages that carry per-page CSS, for the page_css retirement decision."""
    pages = CMSPage.objects.exclude(page_css="").order_by("route").only("slug", "route", "status", "page_css")
    return [
        {"slug": page.slug, "route": page.route, "status": page.status, "page_css_length": len(page.page_css)}
        for page in pages
    ]


def drift_report(seed_path=None) -> dict:
    path = Path(seed_path or SEED_PATH)
    seeds = load_seed_sheets(path)
    sheets = [describe_sheet(sheet, seeds) for sheet in StyleSheet.objects.order_by("sort_order", "name")]
    present = {entry["name"] for entry in sheets}
    missing = [name for name in seeds if name not in present]
    return {
        "seed_path": str(path),
        "seed_found": path.exists(),
        "sheets": sheets,
        "missing_from_database": missing,
        # A re-sync migration recreates these with update_or_create and serves them again.
        "deleted_active_seed_sheets": [
            name for name in missing if seeds[name].get("is_active", True) and name not in RETIRED_SHEETS
        ],
        "pages_with_css": pages_with_css(),
        "counts": dict(Counter(entry["status"] for entry in sheets)),
    }


def is_drifted(entry: dict) -> bool:
    """Would a re-sync migration change what this sheet serves, or is it served CSS the seed lacks?

    True for an active sheet whose CSS differs from the seed or is not in it, for any seed sheet
    whose ``is_active`` or ``sort_order`` changed (deactivating a seed sheet counts), and for a
    retired sheet switched back on. False for a sheet that is inactive in the seed and in the
    database, an inactive unmanaged sheet, an inactive backup copy and a retired sheet that is off.
    """
    if entry["changed_settings"]:
        return True
    return entry["is_active"] and entry["status"] in (STATUS_EDITED, STATUS_UNMANAGED)


def drifted_sheets(report: dict) -> list[str]:
    """Names of drifted sheets, plus ``"<name> (deleted)"`` for each active seed sheet deleted here."""
    drifted = [entry["name"] for entry in report["sheets"] if is_drifted(entry)]
    drifted += [f"{name} (deleted)" for name in report.get("deleted_active_seed_sheets", [])]
    return drifted


def has_drift(report: dict) -> bool:
    return bool(drifted_sheets(report))


def serialize_sheet(sheet) -> dict:
    return {
        "name": sheet.name,
        "display_name": sheet.display_name,
        "description": sheet.description,
        "css": sheet.css,
        "is_active": sheet.is_active,
        "sort_order": sheet.sort_order,
    }


def export_rows() -> dict:
    """Every sheet plus every page's page_css, in the admin import bundle shape (version 1)."""
    pages = CMSPage.objects.exclude(page_css="").order_by("route").only("slug", "route", "page_css")
    return {
        "version": 1,
        "exported_at": timezone.now().isoformat(),
        "stylesheets": [serialize_sheet(sheet) for sheet in StyleSheet.objects.order_by("sort_order", "name")],
        "pages_with_css": [{"slug": page.slug, "route": page.route, "page_css": page.page_css} for page in pages],
    }

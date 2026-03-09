"""
Verify Google Sheets connectivity for the membership spreadsheet.

Steps (matching deployment checklist):
    1. List all worksheet names and their header rows.
    2. Identify the Members worksheet and (if present) the Logs worksheet.
    3. Read a few data rows from the Members worksheet to confirm read access.
    4. If a Logs worksheet exists, append a single test row:
           TEST | Django connection test | <current datetime>
       then read back the last row to confirm write access.
    5. If no Logs worksheet exists, DO NOT write to Members. Instead, report that
       read access works but there is no safe log sheet for a write test.

Notes:
    - This command intentionally prints raw API results and errors to stdout/stderr
      for operator inspection, but never prints secrets from settings or .env.
"""

from __future__ import annotations

import traceback
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

from core.services import google_sheets as sheets

_TZ = ZoneInfo("America/Los_Angeles")


class Command(BaseCommand):
    help = "Verifies Google Sheets membership spreadsheet access (read + optional logs write)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=== Verifying membership Google Sheets configuration ==="))

        try:
            client = sheets._get_client()  # type: ignore[attr-defined]
            spreadsheet_id = sheets._get_spreadsheet_id()  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.ERROR("Failed to build Sheets client or resolve spreadsheet ID."))
            self.stderr.write(f"Exception type: {type(exc).__name__}")
            self.stderr.write("Traceback:")
            self.stderr.write(traceback.format_exc())
            return

        # ------------------------------------------------------------------
        # 1. Inspect available worksheets and their header rows
        # ------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.NOTICE("1) Listing worksheets and header rows"))

        try:
            metadata = client.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheet_entries = metadata.get("sheets", []) or []
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.ERROR("Failed to fetch spreadsheet metadata from Sheets API."))
            self.stderr.write(f"Exception type: {type(exc).__name__}")
            self.stderr.write("Traceback:")
            self.stderr.write(traceback.format_exc())
            return

        worksheet_headers: dict[str, list[str]] = {}

        if not sheet_entries:
            self.stderr.write(self.style.ERROR("Spreadsheet contains no worksheets."))
            return

        for sheet_entry in sheet_entries:
            title = sheet_entry.get("properties", {}).get("title", "<unnamed>")
            try:
                response = client.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=f"{title}!1:1",
                ).execute()
                header_row = response.get("values", [[]])
                headers = [str(h) for h in (header_row[0] if header_row else [])]
            except Exception as exc:  # noqa: BLE001
                headers = []
                self.stderr.write(
                    self.style.WARNING(
                        f"  Failed to read header row for worksheet '{title}': {type(exc).__name__}"
                    )
                )
            worksheet_headers[title] = headers

        self.stdout.write("Discovered worksheets and header rows:")
        for title, headers in worksheet_headers.items():
            self.stdout.write(f"  - '{title}': {headers!r}")

        # ------------------------------------------------------------------
        # 2. Identify Members + Logs worksheets
        # ------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.NOTICE("2) Identifying Members and Logs worksheets"))

        members_sheet: str | None = None
        logs_sheet: str | None = None

        # Heuristic: Members sheet contains common membership fields.
        for title, headers in worksheet_headers.items():
            header_set = {h.strip().lower() for h in headers}
            if {"first name", "last name"} <= header_set and (
                "primary email" in header_set or "email" in header_set
            ):
                members_sheet = title
                break

        # Logs sheet is expected to start with Order | Transaction | DateTime
        for title, headers in worksheet_headers.items():
            normalized = [h.strip().lower() for h in headers]
            if len(normalized) >= 3 and normalized[0] == "order" and normalized[1] == "transaction":
                # DateTime header from legacy sheet may be "DateTime" or "datetime"
                if normalized[2] in {"datetime", "date/time", "date time"}:
                    logs_sheet = title
                    break

        self.stdout.write(f"  Detected Members worksheet: {members_sheet!r}")
        self.stdout.write(f"  Detected Logs worksheet: {logs_sheet!r}")

        if not members_sheet:
            self.stderr.write(
                self.style.ERROR(
                    "Could not heuristically identify a Members worksheet. "
                    "Please review the worksheet list above and update this command if needed."
                )
            )
            return

        # ------------------------------------------------------------------
        # 3. Confirm read access by reading a few rows from Members
        # ------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(
            self.style.NOTICE(f"3) Reading a few rows from Members worksheet '{members_sheet}'")
        )

        try:
            records: list[dict[str, Any]] = sheets.get_all_records(members_sheet)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(
                self.style.ERROR(
                    f"Failed to read records from Members worksheet '{members_sheet}'."
                )
            )
            self.stderr.write(f"Exception type: {type(exc).__name__}")
            self.stderr.write("Traceback:")
            self.stderr.write(traceback.format_exc())
            return

        self.stdout.write(f"  Total member records returned: {len(records)}")
        preview_count = min(3, len(records))
        self.stdout.write(f"  Previewing first {preview_count} record(s):")
        for idx, record in enumerate(records[:preview_count], start=1):
            self.stdout.write(f"    [{idx}] {record!r}")

        # ------------------------------------------------------------------
        # 4. If Logs worksheet exists, append + read back a test row
        # ------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.NOTICE("4) Verifying Logs write access (if Logs worksheet exists)"))

        if not logs_sheet:
            self.stdout.write(
                self.style.WARNING(
                    "No Logs worksheet detected; skipping write test to avoid touching Members."
                )
            )
            self.stdout.write(
                "Result: READ access to Members verified; no safe Logs sheet detected for write test."
            )
            return

        # Build test row: [TEST, Django connection test, <current datetime in PT>]
        now_str = datetime.now(_TZ).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p %Z")
        test_row = ["TEST", "Django connection test", now_str]
        self.stdout.write(
            f"  Appending test row to Logs worksheet '{logs_sheet}': {test_row!r}"
        )

        try:
            sheets.append_row(logs_sheet, test_row)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(
                self.style.ERROR(
                    f"Failed to append test row to Logs worksheet '{logs_sheet}'."
                )
            )
            self.stderr.write(f"Exception type: {type(exc).__name__}")
            self.stderr.write("Traceback:")
            self.stderr.write(traceback.format_exc())
            return

        # Read back the last row to confirm write success.
        self.stdout.write("  Reading back last row from Logs to confirm write...")
        try:
            # Use column 1 to determine last row index, then read that row.
            all_order_values = sheets.get_column_values(logs_sheet, col=1)
            last_row_index = len(all_order_values)
            last_row_values = sheets.get_row_values(logs_sheet, row=last_row_index)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(
                self.style.ERROR(
                    f"Failed to read back last row from Logs worksheet '{logs_sheet}'."
                )
            )
            self.stderr.write(f"Exception type: {type(exc).__name__}")
            self.stderr.write("Traceback:")
            self.stderr.write(traceback.format_exc())
            return

        self.stdout.write(f"  Last row index in Logs: {last_row_index}")
        self.stdout.write(f"  Last row values: {last_row_values!r}")

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Verification complete: READ access to Members and WRITE access to Logs confirmed."
            )
        )


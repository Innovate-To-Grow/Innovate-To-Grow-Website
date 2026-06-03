from datetime import datetime, timezone

from flask import (
    flash,
)
from gspread.cell import Cell

from project import get_wks_columns, get_wks_records, prospects, wks
from project.utils.utils import clean_phone_number


def get_current_datetime() -> str:
    """
    Returns the current datetime as a string in UTC
    """

    now_utc = datetime.now(timezone.utc)
    formatted_time = now_utc.strftime("%m/%d/%Y %H:%M:%S")
    return formatted_time


def check_prospects():
    """
    Checks the prospects spreadsheet for people who are already members
    and adds notes specifiying conflicts
    """

    wks_records: list[dict] = get_wks_records(wks)
    prospect_records: list[dict] = get_wks_records(prospects)
    prospect_columns: dict = get_wks_columns(prospects)

    primary_emails = {}
    secondary_emails = {}
    phone_numbers = {}

    num_primary_emails_conflicted: int = 0
    num_secondary_emails_conflicted: int = 0
    num_phone_numbers_conflicted: int = 0

    conflicted_primary_emails: list[str] = []
    conflicted_secondary_emails: list[str] = []
    conflicted_phone_numbers: list[str] = []

    when_last_checked: str = "When last checked?"
    when_signed_up_as_member: str = "When signed up as member?"
    when_started: str = "When Started"
    collison: str = "Collision?"
    secondary_collison: str = "Secondary Collision"
    phone_collision: str = "Phone Collision"
    notes_col: str = "Notes"

    cells_to_update: list[Cell] = []

    # --- Creating dictionaries for quick search later --- #
    for row in wks_records:
        row_number: int = row["Row"]

        p_email = str(row.get("Primary Email", "")).strip().lower()
        if p_email:
            primary_emails[p_email] = row_number

        s_email = str(row.get("Secondary Email", "")).strip().lower()
        if s_email:
            secondary_emails[s_email] = row_number

        raw_phone = str(row.get("Phone Number", ""))
        clean_phone = clean_phone_number(raw_phone)
        if clean_phone:
            phone_numbers[clean_phone] = row_number

    for row in prospect_records:
        # --- If a prospect is already a member, we can skip them --- #
        if row.get(when_signed_up_as_member, "") != "":
            continue

        row_number = row["Row"]

        # --- Creating cell for "When last checked?" column --- #
        if when_last_checked in prospect_columns:
            last_checked_cell = Cell(
                row_number, prospect_columns[when_last_checked], get_current_datetime()
            )
            cells_to_update.append(last_checked_cell)

        email = str(row.get("Email", "")).strip().lower()
        secondary_email = str(row.get("Secondary Email (optional)", "")).strip().lower()
        phone_number = str(row.get("Phone Number (optional)", ""))
        cleaned_prospect_phone = clean_phone_number(phone_number)

        notes = []
        is_member = False
        member_row_idx = None

        # 1. Primary Email Check
        if email:
            if email in primary_emails:
                num_primary_emails_conflicted += 1
                conflicted_primary_emails.append(email)

                member_row_idx = primary_emails[email]
                # Access member record (row index - 2 because records start at row 2 and list is 0-indexed)
                full_row = (
                    wks_records[member_row_idx - 2]
                    if (member_row_idx - 2) < len(wks_records)
                    else None
                )

                if full_row:
                    member_start_date = full_row.get(when_started, "")
                    if not member_start_date:
                        member_start_date = "Email exists in Members as a primary, but no value in When Started"

                    if when_signed_up_as_member in prospect_columns:
                        cells_to_update.append(
                            Cell(
                                row_number,
                                prospect_columns[when_signed_up_as_member],
                                member_start_date,
                            )
                        )

                    notes.append(
                        f"Primary email found as Primary Email in Members (Row {member_row_idx})."
                    )
                    is_member = True

                if collison in prospect_columns:
                    cells_to_update.append(
                        Cell(row_number, prospect_columns[collison], "TRUE")
                    )

            elif email in secondary_emails:
                num_primary_emails_conflicted += 1
                conflicted_primary_emails.append(email)

                member_row_idx = secondary_emails[email]
                full_row = (
                    wks_records[member_row_idx - 2]
                    if (member_row_idx - 2) < len(wks_records)
                    else None
                )

                if full_row:
                    member_start_date = full_row.get(when_started, "")
                    if not member_start_date:
                        member_start_date = "Email exists in Members as a secondary, but no value in When Started"

                    if when_signed_up_as_member in prospect_columns:
                        cells_to_update.append(
                            Cell(
                                row_number,
                                prospect_columns[when_signed_up_as_member],
                                member_start_date,
                            )
                        )

                    notes.append(
                        f"Primary email found as Secondary Email in Members (Row {member_row_idx})."
                    )
                    is_member = True

                if collison in prospect_columns:
                    cells_to_update.append(
                        Cell(row_number, prospect_columns[collison], "TRUE")
                    )

        # 2. Secondary Email Check
        if secondary_email:
            # Check against Primary Emails in Members
            if secondary_email in primary_emails:
                match_row_idx = primary_emails[secondary_email]
                if match_row_idx != member_row_idx:
                    num_secondary_emails_conflicted += 1
                    conflicted_secondary_emails.append(secondary_email)
                    if secondary_collison in prospect_columns:
                        cells_to_update.append(
                            Cell(
                                row_number, prospect_columns[secondary_collison], "TRUE"
                            )
                        )
                    notes.append(
                        f"Secondary email found as Primary Email in Members (Row {match_row_idx})."
                    )

            # Check against Secondary Emails in Members
            if secondary_email in secondary_emails:
                match_row_idx = secondary_emails[secondary_email]
                if match_row_idx != member_row_idx:
                    num_secondary_emails_conflicted += 1
                    conflicted_secondary_emails.append(secondary_email)
                    if secondary_collison in prospect_columns:
                        cells_to_update.append(
                            Cell(
                                row_number, prospect_columns[secondary_collison], "TRUE"
                            )
                        )
                    notes.append(
                        f"Secondary email found as Secondary Email in Members (Row {match_row_idx})."
                    )

        # 3. Phone Check
        if cleaned_prospect_phone and cleaned_prospect_phone in phone_numbers:
            match_row_idx = phone_numbers[cleaned_prospect_phone]
            if match_row_idx != member_row_idx:
                num_phone_numbers_conflicted += 1
                conflicted_phone_numbers.append(phone_number)
                if phone_collision in prospect_columns:
                    cells_to_update.append(
                        Cell(row_number, prospect_columns[phone_collision], "TRUE")
                    )
                notes.append(f"Phone number found in Members (Row {match_row_idx}).")

        # Update Notes
        if notes and notes_col in prospect_columns:
            # If existing notes exist, append? For now overwrite or append to empty string in logic
            # We'll just overwrite with new findings as this is a "check" operation
            cells_to_update.append(
                Cell(row_number, prospect_columns[notes_col], " ".join(notes))
            )

    if cells_to_update:
        prospects.update_cells(cells_to_update)

    flash(
        f"Found conflicts - Primary: {num_primary_emails_conflicted}, Secondary: {num_secondary_emails_conflicted}, Phone: {num_phone_numbers_conflicted}"
    )
    print(
        f"Conflicts:\nPrimary Emails: {conflicted_primary_emails}\nSecondary Emails: {conflicted_secondary_emails}\nPhone Numbers: {conflicted_phone_numbers}"
    )

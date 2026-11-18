"""What the old snapshot reader left on a managed worksheet.

It asked Google only for spreadsheet- and sheet-level developer metadata, so it never saw the entries it had put on
columns and on the header row. Every sync therefore bound every column again from its header label and added a fresh
copy of the event's entries at the same places, until the sheet's 30,000 characters were used up and Google rejected
the next write (the failing ``event.registration_sheet_sync`` jobs).
"""

from copy import deepcopy

from apps.event.tests.services.registration_sheet.managed.sheet_fakes import METADATA_LIMIT, metadata_size


def add_copies(sheet, entries, runs=1):
    """Append ``runs`` copies of ``entries`` to the sheet: new ids, same keys, values and places."""
    spreadsheet = sheet.spreadsheet
    for _ in range(runs):
        for entry in entries:
            spreadsheet.metadata_counter += 1
            sheet.metadata.append({**deepcopy(entry), "metadataId": spreadsheet.metadata_counter})


def fill_to_limit(sheet):
    """One copy of the sheet's entries per old-reader run, for as many runs as the sheet's storage held."""
    entries = deepcopy(sheet.metadata)
    runs = (METADATA_LIMIT - metadata_size(sheet.metadata)) // metadata_size(entries)
    add_copies(sheet, entries, runs)
    return entries, runs


def add_other_tool_metadata(sheet, *, room):
    """Another tool's entry on the worksheet, leaving ``room`` characters of the sheet's metadata storage free."""
    key = "com.example.other-tool"
    length = METADATA_LIMIT - metadata_size(sheet.metadata) - room - len(key)
    assert length >= 0, "the sheet has too little room left for the entry's key"
    span = {"sheetId": sheet.id, "dimension": "COLUMNS", "startIndex": 25, "endIndex": 26}
    sheet.spreadsheet.metadata_counter += 1
    identity = sheet.spreadsheet.metadata_counter
    sheet.metadata.append(
        {
            "metadataId": identity,
            "metadataKey": key,
            "metadataValue": "x" * length,
            "location": {"dimensionRange": span},
        }
    )


def old_reader_run(entries):
    """The createDeveloperMetadata requests one more old-reader sync sent for ``entries``."""
    return [
        {"createDeveloperMetadata": {"developerMetadata": {k: v for k, v in entry.items() if k != "metadataId"}}}
        for entry in entries
    ]

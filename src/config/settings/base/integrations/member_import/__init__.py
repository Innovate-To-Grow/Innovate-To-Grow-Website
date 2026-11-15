"""
Member import (Admin → Members → Import): how big an upload may be and how long a staged import is kept.

An upload is parsed and analysed into a batch (``authn.MemberImportBatch``) that an admin reviews before anything is
written. Every value is an app default; each comment says what it does. Making them editable in the admin is a later
phase of the import plan.
"""

MEMBER_IMPORT = {
    # An upload that was not applied (still in review, or discarded) is deleted this many hours after the upload.
    "batch_lifetime_hours": 24,
    # Most data rows one upload may have. The apply runs in one request and one transaction, so a bigger sheet is
    # refused at upload with "split the file".
    "max_rows": 2000,
    # Most rows read from the sheet, blank ones included, before the upload is refused. Reading stops there, so a
    # small but highly compressed workbook can't expand into millions of rows in a web worker.
    "max_rows_read": 100_000,
    # Days an applied import keeps each row's sheet values and the member snapshot its review showed.
    "values_retention_days": 30,
    # Days an applied import is kept at all: who chose what for each row, and what happened.
    "rows_retention_days": 365,
    # An upload of a file (same SHA-256) applied within this many days is flagged as a repeat.
    "repeat_warning_days": 30,
    # Batches deleted, or blanked, per purge statement (the worker's hourly maintenance and each upload page visit).
    "purge_batch_size": 50,
}

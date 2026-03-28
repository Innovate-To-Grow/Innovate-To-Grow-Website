# Troubleshooting Google Sheets

## Common failures

- Missing credentials or malformed JSON
- Invalid spreadsheet or worksheet identifiers
- Unexpected column layout changes
- Expired or revoked service-account permissions
- Empty cache after a slug or schema change

## What to check

- Confirm the active `GoogleSheetSource` record is correct.
- Verify environment variables or stored credentials are present.
- Re-run the relevant import or display path after clearing stale cache.
- Inspect logs for `GoogleSheetsConfigError` and related parsing failures.

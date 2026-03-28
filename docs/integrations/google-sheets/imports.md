# Database Imports

## Project imports

- Project import workflows transform rows into semester and project records.
- Imports should preserve semester identity and update matching projects instead of duplicating them.
- Template downloads and import endpoints stay authenticated.

## Operational flow

1. Upload a supported spreadsheet.
2. Validate columns and required identifiers.
3. Normalize row values.
4. Create or update semesters and projects.
5. Report counts for created, updated, and skipped rows.

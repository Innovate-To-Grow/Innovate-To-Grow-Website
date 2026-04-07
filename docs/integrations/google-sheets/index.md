# Google Sheets Integration

Google Sheets is used for two distinct purposes: syncing event registration data out to a spreadsheet, and importing schedule/project data from a spreadsheet into the database.

## In this section

- [Data Flow](data-flow.md) — How data moves between Django and Google Sheets
- [Operations](operations.md) — Setup, troubleshooting, and operational guidance

## Who this is for

Engineers maintaining the event registration pipeline, admins configuring Google Sheets sync, and anyone debugging data sync issues.

## Overview

| Integration | Direction | Trigger | Service |
|-------------|-----------|---------|---------|
| Registration sync | Django → Sheets | On registration creation | `src/event/services/registration_sheet_sync.py` |
| Schedule sync | Sheets → Django | Admin action or management | `src/event/services/schedule_sync.py` |

Both integrations authenticate via a Google service account whose credentials are stored in the `GoogleCredentialConfig` model (managed through Django admin).

## Libraries

| Package | Version | Purpose |
|---------|---------|---------|
| `gspread` | 5.5.0 | Google Sheets API client |
| `google-auth` | 2.35.0 | Service account authentication |
| `google-api-python-client` | 2.170.0 | Google API discovery client |

## Authentication

Credentials are stored in `GoogleCredentialConfig` (`src/core/models/service_credentials.py`) as a JSON text field containing a Google service account key. The model validates that the JSON includes:

- `type`
- `project_id`
- `private_key`
- `client_email`
- `token_uri`

Only one `GoogleCredentialConfig` can be active at a time. The `load()` class method returns the active configuration. If no config exists or credentials are invalid, sync operations fail gracefully with logged errors.

The service account email must be granted **Editor** access to target spreadsheets.

## Related sections

- [Architecture: Integrations](../../architecture/integrations.md) — All external service connections
- [API: Events](../../api/events.md) — Event registration endpoints
- [Deployment: Environments](../../deployment/environments.md) — Environment variable reference

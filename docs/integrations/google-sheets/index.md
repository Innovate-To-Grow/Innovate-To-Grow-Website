# Google Sheets Integration

Google Sheets is used for several purposes: syncing event registration data out to a spreadsheet, importing schedule/project data from a spreadsheet into the database, and importing the historical past-projects catalog into the database for the public `/past-projects` page.

## In this section

- [Data Flow](data-flow.md) — How data moves between Django and Google Sheets
- [Operations](operations.md) — Setup, troubleshooting, and operational guidance

## Who this is for

Engineers maintaining the event registration pipeline, admins configuring Google Sheets sync, and anyone debugging data sync issues.

## Overview

| Integration | Direction | Trigger | Service |
|-------------|-----------|---------|---------|
| Registration sync | Outbox worker → Sheets | Durable job created with registration | `src/apps/event/services/registration_sheet_sync/` |
| Schedule sync | Sheets → Django | Admin action or management | `src/apps/event/services/schedule_sync.py` |
| Past-projects sync | Sheets → Django | Admin Pull / cron | `src/apps/projects/services/sheet_sync/` |

Both integrations authenticate via a Google service account whose credentials are stored in the `GoogleCredentialConfig` model (managed through Django admin).

## Libraries

| Package | Version | Purpose |
|---------|---------|---------|
| `gspread` | 6.2.1 | Google Sheets API client |
| `google-auth` | 2.56.2 | Service account authentication |
| `google-api-python-client` | 2.198.0 | Google API discovery client |

## Authentication

Credentials are stored in `GoogleCredentialConfig`
(`src/apps/core/models/base/service_credentials/google.py`) as a JSON text
field containing a Google service account key. The model validates that the
JSON includes:

- `type`
- `project_id`
- `private_key`
- `client_email`
- `token_uri`

Only one `GoogleCredentialConfig` can be active at a time, enforced by a
partial database unique constraint. `load()` returns only that explicit active
configuration. If it is missing or invalid, sync jobs fail closed and retain
the error for operators.

The service account email must be granted **Editor** access to target spreadsheets.

## Related sections

- [Architecture: Integrations](../../architecture/integrations.md) — All external service connections
- [API: Events](../../api/events.md) — Event registration endpoints
- [Deployment: Environments](../../deployment/environments.md) — Environment variable reference

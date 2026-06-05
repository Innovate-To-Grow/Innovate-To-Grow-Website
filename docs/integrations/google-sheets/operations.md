# Google Sheets Operations

Setup, configuration, and troubleshooting for the Google Sheets integration.

## Initial setup

### 1. Create a Google service account

1. Go to the Google Cloud Console
2. Create or select a project
3. Enable the Google Sheets API
4. Create a service account under IAM & Admin → Service Accounts
5. Generate a JSON key for the service account
6. Download the key file

### 2. Configure credentials in Django admin

1. Navigate to Django admin → Core → Google Credential Configs
2. Create a new config
3. Paste the entire JSON key file contents into the credentials field
4. Save — the model validates required fields (`type`, `project_id`, `private_key`, `client_email`, `token_uri`)
5. Ensure the config is marked as active (only one can be active)

### 3. Grant spreadsheet access

Share each target Google Sheet with the service account's email address (found in the `client_email` field of the JSON key). Grant **Editor** access.

### 4. Configure event sheets

In Django admin → Events → Event:
1. Set `registration_sheet_id` to the Google Sheets document ID (from the URL: `docs.google.com/spreadsheets/d/{THIS_PART}/edit`)
2. Set `registration_sheet_gid` to the worksheet GID (from the URL: `#gid={THIS_PART}`)

### 5. Configure the past-projects sheet

In Django admin → **Projects → Past Projects Sheet**:
1. Add a config, set `Google Sheet ID` (the `/d/{THIS_PART}/` part of the URL) and `Worksheet Name`
   (the tab name, e.g. `Past-Projects-WEB-LIVE`), and mark it **Active**.
2. Share the sheet with the service-account `client_email` — **Viewer** access is sufficient (this sync only
   reads).
3. Click **Pull Past Projects** to import now. The changelist shows the active Google service account so you can
   confirm which email to share with.

The expected columns are `Year-Semester`, `Class`, `Team#`, `Team Name`, `Project Title`, `Organization`,
`Industry`, `Abstract`, `Student Names`. If the live header text differs, adjust `COLUMN_MAP` in
`src/apps/projects/services/sheet_sync/runner.py` (print `worksheet.row_values(1)` in a Django shell to see the
exact header strings — the legacy export used non-breaking spaces in some headers).

**Sync semantics:** a sync is a **full replace of sheet-sourced rows only**. Every `Project` with
`source="sheet"` is deleted and recreated from the sheet; manual/CSV rows (`source="manual"`) are never touched,
even when they share a semester with the sheet. If the fetch yields no importable rows, the sync aborts **before**
deleting anything.

**Bootstrap order / visibility:** the public `/projects/past-all/` API hides the newest *published* semester
(treated as the in-flight "current" semester owned by the event flow). The past-projects sheet is historical and
should not contain the current event semester. Configure/publish the current event semester first, otherwise the
most recent synced semester is hidden as "current".

#### Scheduled auto-sync

This repo ships **no scheduler**. To auto-sync, enable **Auto Sync** + set an interval on the config, then run the
management command externally (e.g. an ECS scheduled task or host crontab), recommended daily:

```bash
python manage.py sync_past_projects        # syncs only if the interval has elapsed (sync_is_due)
python manage.py sync_past_projects --force # sync regardless of the interval
```

The command self-gates on `sync_is_due`, so over-scheduling is safe. Before a deploy that relies on it, confirm
credentials with `python manage.py verify_service_configs --strict --require-google`.

## Configuring credentials

Google service-account credentials are stored in the database via [`GoogleCredentialConfig`](../../../src/apps/core/models/base/service_credentials/google.py). Paste the service-account JSON into Django admin → Site Settings → Google Credential Configs and mark the config as active. No process env vars are required, and the ECS task definition no longer carries `GOOGLE_SHEETS_*` keys.

## Troubleshooting

### Sync not working

1. **Check credentials:** Verify `GoogleCredentialConfig` is active and has valid JSON in Django admin
2. **Check permissions:** Ensure the service account email has Editor access to the target sheet
3. **Check event config:** Verify `registration_sheet_id` and `registration_sheet_gid` are set on the Event
4. **Check sync logs:** Review `RegistrationSheetSyncLog` (registration), `ScheduleSyncLog` (schedule), or `PastProjectSyncLog` (past projects) in Django admin for error messages
5. **Check application logs:** Look for gspread or Google API errors in the console/CloudWatch

### Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `SpreadsheetNotFound` | Sheet ID is wrong or service account lacks access | Verify ID and sharing permissions |
| `WorksheetNotFound` | GID doesn't match any worksheet in the spreadsheet | Check the GID in the sheet URL |
| `APIError 429` | Google Sheets API rate limit exceeded | Wait and retry; the debounce mechanism should prevent this |
| `InvalidCredentials` | JSON key is malformed or expired | Re-generate the service account key |
| No `GoogleCredentialConfig` found | No active config in database | Create one in Django admin |

### Data drift

If sheet data doesn't match database records:

1. Use the "Full replace sync" admin action on the Event model
2. This overwrites all sheet rows with current database state
3. Verify the sheet after sync completes

### Local development

For local testing without Google API access:
- Registration sync will log a warning and skip silently if no `GoogleCredentialConfig` is configured
- This does not block registration creation — the primary operation always succeeds

## Monitoring

In production, monitor:
- `RegistrationSheetSyncLog` records for failed syncs
- CloudWatch logs for Google API errors
- Google Sheets API quotas in Google Cloud Console

## Related pages

- [Data Flow](data-flow.md) — Technical sync details
- [Deployment: Environments](../../deployment/environments.md) — Full environment variable reference
- [CMS & Admin: Operations](../../cms-admin/operations.md) — General operational guidance

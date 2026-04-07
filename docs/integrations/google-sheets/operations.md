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

## Environment variables

Two authentication methods are supported:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | Full service account JSON (preferred, used in production ECS task) |
| `GOOGLE_SHEETS_API_KEY` | Simple API key (read-only fallback) |

In production, `GOOGLE_SHEETS_CREDENTIALS_JSON` is injected via the ECS task definition (`aws/task-definition.json`).

For local development, configure credentials through the Django admin `GoogleCredentialConfig` model rather than environment variables.

## Troubleshooting

### Sync not working

1. **Check credentials:** Verify `GoogleCredentialConfig` is active and has valid JSON in Django admin
2. **Check permissions:** Ensure the service account email has Editor access to the target sheet
3. **Check event config:** Verify `registration_sheet_id` and `registration_sheet_gid` are set on the Event
4. **Check sync logs:** Review `RegistrationSheetSyncLog` in Django admin for error messages
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

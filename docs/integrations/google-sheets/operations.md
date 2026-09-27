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

In Django admin → Events → Event, choose **Manage sync**:

1. Set the Google Sheets document ID (the `/d/{ID}/` part of the URL) and worksheet
   GID (`#gid={GID}`). Share the document with the configured service account.
2. Set the header row and choose automatic, interval, or manual synchronization.
   Automatic batching defaults to a 15-second quiet window with a 60-second cap.
3. Select the fields to synchronize. Changing a display label explicitly updates
   that header on the next sync. Later renames made directly in Google Sheets are
   preserved until the configured label changes again.
4. Use **Check connection** and **Preview changes**. These actions read Google
   Sheets but do not modify its content.
5. Resolve ambiguous initial field mappings using the column selectors. After a
   field is bound, move its whole column in Google Sheets to relocate it. Preview
   again after changing the destination, header row, or mappings.
6. Choose **Sync now** to queue a non-destructive reconciliation, or review the
   legacy adoption action when existing rows have no registration IDs, or when
   rows belong to registrations deleted before managed sync (adoption marks
   those rows Deleted).

The system maintains a protected, hidden `Registration ID` column. It does not
need to be the last column. You can rename visible headers, reorder whole
columns, and add custom columns. Notes, formulas, and formatting in custom columns
are preserved. Use complete-row sorts so identities and annotations stay together.
Do not delete or overwrite the identity column or copy only part of a record.

Registration, ticket, question, and relevant event changes mark the sheet as
pending. Manual mode records pending changes without automatically writing them.
Interval mode batches changed data; it does not perform empty periodic exports.
The management page shows the next eligible run, latest results, and recent logs.

If the worksheet ID was left empty, the first successful sync pins the resolved
worksheet ID. Reordering spreadsheet tabs therefore does not move the destination.

Run the durable background worker (without it, an in-process timer runs syncs that
do not survive a process restart):

```bash
python manage.py run_background_worker
```

Queueing work does not prove that a provider write succeeded. Confirm the run
result, row counts, and the resulting worksheet after an authorized production
rollout. Provider failures and worker load may delay a run beyond its configured
batching window.

For a rollout, apply the additive migration and finish updating all web processes
and background workers before adopting managed sheets. Older exporters do not
understand the new column mappings and must not run against managed worksheets.

### 5. Configure the current-project schedule sheet(s)

In Django admin → **Events → Current Project and Schedule**, add one row per event schedule you want to
publish (e.g. one per year — put the year in the **Event Name**, it is what CMS editors pick from):
1. Set `Google Sheet ID`, `Tracks Worksheet GID` and `Projects Worksheet GID` for **that** schedule's sheet.
2. Share the sheet with the service-account `client_email` (**Viewer** is sufficient).
3. Mark exactly one row **Active** — it backs `/schedule` when no schedule is selected, `/event/projects/`
   and the assistant context. Other rows stay available for CMS embeds.
4. Sync it: **Pull Current Projects & Schedule** (changelist button) pulls the *active* row; the
   **Sync from Google Sheets** action on each row (and on the change form) pulls *that* row from its own sheet,
   so previous years can be refreshed without activating them.

#### Schedule auto-sync

Each row has its own **Auto Sync** toggle and interval. A schedule that stops being active — because you activate
another one (allowed in one step; the previous row is archived automatically) or untick **Active** on it — has
Auto Sync switched **off**, so a past year is never re-pulled from a sheet that may since have been repurposed.
Re-enable it on that row deliberately if you still want it refreshed. Run the command externally (cron / ECS
scheduled task):

```bash
python manage.py sync_schedule                       # cron mode: every schedule whose auto-sync is enabled and due (active first)
python manage.py sync_schedule --force               # the active schedule now, regardless of its interval
python manage.py sync_schedule --schedule <uuid>     # one specific schedule now (any row; its auto-sync settings are ignored)
```

In cron mode one failing sheet does not stop the others; the command still exits non-zero and names every failed
schedule. A failed auto-sync attempt counts toward that row's interval, so a broken or unshared sheet is retried
(and reported) once per interval rather than on every tick — fix the sheet, or switch that row's Auto Sync off.

### 6. Configure the past-projects sheet

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
| `APIError 429` | Google Sheets API rate limit exceeded | Let the durable job retry with backoff; inspect queue age and quota before an explicit retry |
| `InvalidCredentials` | JSON key is malformed or expired | Re-generate the service account key |
| No `GoogleCredentialConfig` found | No active config in database | Create one in Django admin |
| Missing `Registration ID` | Legacy worksheet requires a reviewed identity mapping | Open Manage sync, preview the legacy row matches, then adopt or create a fresh worksheet |
| Duplicate field binding or registration ID | Conflicting column metadata or copied identities | Resolve the specific columns or rows listed in the preview and preview again |
| Missing managed header row | A previously bound header row was deleted | Restore the original header row and mapping, or create a fresh managed worksheet after previewing recovery |

### Data drift

If sheet data does not match database records:

1. Open **Manage sync** for the affected Event and select **Preview changes**.
2. Review inserted, updated, unchanged, deleted, and conflicting records.
3. Resolve identity or column conflicts before proceeding. Never assign identities
   by guessing from a person's name or email alone.
4. Use **Sync now** to update managed cells while retaining custom content.
5. For a populated legacy sheet, inspect the row-match preview and use the
   separately reviewed adoption action. A backup is created before identities
   are written.
6. If adoption is impossible, create a fresh managed worksheet. The original tab
   remains available, and the event switches only after the new sheet is ready.
7. After an authorized live run, inspect the backup/new tab, unique registration
   IDs, representative updated values, and preserved custom cells separately.

If Google accepts a write but the database transaction fails, the failure log
records that distinction and any created backup or worksheet IDs. Those tabs are
retained for inspection. An ordinary retry reconciles existing registration IDs;
if an interrupted write leaves an unknown identity, review the conflict or use
the fresh-worksheet recovery action instead of assigning an identity by guesswork.

### Local development

Use an isolated database and mock the Google provider in tests. Do not seed real
service-account credentials into that database. Automatic scheduling is durable
and does not start a background timer inside the web process; queued jobs run
only when a worker processes them. A missing active `GoogleCredentialConfig`
fails closed and is shown on the management page.

## Monitoring

In production, monitor:
- `RegistrationSheetSyncLog` records for failed syncs
- Background worker heartbeat, queue depth, oldest-job age, and failed jobs
- CloudWatch logs for Google API errors
- Google Sheets API quotas in Google Cloud Console

## Related pages

- [Data Flow](data-flow.md) — Technical sync details
- [Deployment: Environments](../../deployment/environments.md) — Full environment variable reference
- [CMS & Admin: Operations](../../cms-admin/operations.md) — General operational guidance

# Google Sheets Data Flow

How data moves between the Django backend and Google Sheets.

## Registration sync (Django → Sheets)

**Service:** `src/apps/event/services/registration_sheet_sync/`

Registration sync is a one-way projection of database records into managed
spreadsheet cells. It inserts missing registrations, updates existing ones by
registration UUID, and preserves columns that belong to spreadsheet editors.

### Configuration and management

Open an Event and select **Manage sync**. The dedicated management page contains
connection settings, synchronization timing, field selection and labels, initial
column mappings, a read-only preview, and execution history. Merely opening the
page does not call Google or synchronize data.

`RegistrationSheetSyncConfig` stores per-event settings and durable scheduling
state. Existing Event destination and last-sync fields remain available for
compatibility. New event copies do not inherit a sheet destination or pending
synchronization work.

### Timing and durable work

- **Automatic:** Changes wait for a quiet window (15 seconds by default), capped
  at 60 seconds from the first pending change. Bursts share a pending job.
- **Interval:** Pending changes are collected into a batch with the configured
  delay; later changes do not continuously postpone that batch.
- **Manual:** Changes remain pending until an administrator chooses **Sync now**.

The existing background worker executes durable jobs. When
`BACKGROUND_JOBS_ENABLED` is false, an in-process timer runs the sync after the
source change commits, and the queued job remains as a record. Dirty state and
enqueueing commit or roll back with the source change. A run captures a generation; changes arriving during that run remain
pending for a subsequent run. The scheduling state lock is separate from the lock
that serializes provider writes, so a slow Google request does not hold the
scheduling lock.

Run the database-backed worker in production; the in-process fallback does not
survive a process restart.
The batching delay is an eligibility time, not a delivery deadline: worker load,
provider throttling, and retries can increase the actual delay.

### Stable field identity

Each managed column has Google Sheets developer metadata identifying its field.
Built-in fields use stable keys; custom questions use their UUID, not their
editable wording. The visible header can be renamed, and whole columns can be
moved or inserted without changing field identity. The configured header row is
also recorded in the mapping.

The protected, hidden **Registration ID** column identifies rows and may appear
anywhere. Normal synchronization updates only managed cells; it does not clear
the worksheet or rewrite complete rows containing custom formulas or annotations.
New fields can add columns. Disabled or removed fields are left in place rather
than erased. Writes use literal cell values so attendee input and question labels
cannot become spreadsheet formulas.

An explicit display-label change in the management page updates the bound header
once. Subsequent edits to that visible header in Google Sheets remain intact
until the configured label changes again. New fields in an already managed sheet
receive new columns; they never take over a custom column merely because its
heading matches a question label.

Metadata must be unambiguous. Duplicate field bindings, duplicate registration
IDs, unknown registration IDs, and missing identity anchors produce actionable
conflicts instead of guessed writes. Moving individual cell contents is different
from moving entire columns or sorting complete rows: it can break the relationship
between a row and its notes. Editors should operate on complete records.

### Connecting existing worksheets

An empty worksheet can be initialized automatically. An existing worksheet with
recognizable headers is mapped using unique normalized names and known aliases;
manual column mappings resolve labels the system cannot recognize. Once metadata
exists it takes precedence over visible header wording.

A populated legacy sheet without registration IDs requires a reviewed migration.
The preview displays candidate row matches; only unambiguous matches using a
strong combination of registration fields are eligible. Name-only or email-only
matches are insufficient. Applying the migration backs up the existing worksheet
before binding rows. A stale preview must be refreshed before applying.

If an existing sheet cannot be safely adopted, administrators can create a fresh
managed worksheet. Recovery preserves the original worksheet and backs it up;
it does not clear the active sheet and then attempt a separate replacement write.
The destination switches only after the new worksheet is populated successfully.

### Reconciliation and audit

Every run reconciles a bounded database snapshot with sheet registration IDs.
Retries reread provider state, including after a provider write succeeds but the
local transaction fails, so retrying does not blindly append the same UUID again.
Changed registrations update in place. Deleted registrations are marked only
when a durable receipt establishes that this integration previously synchronized
that identity; an unknown UUID is a conflict, never an inferred deletion.

The management page separates queued/running/attention state from the last
successful synchronization. Audit results distinguish inserted, updated,
unchanged, deleted, and conflicting rows. Temporary provider failures can retry;
schema conflicts require an administrator to review the mapping. Old failures
must not replace the current status of a newer successful run.

Failure logs retain backup and newly created worksheet IDs and indicate whether
Google had already accepted the managed write. This makes partial cross-system
completion inspectable without deleting the original sheet or hiding recovery
artifacts.

Google applies requests within one `spreadsheets.batchUpdate` atomically, but
there is no cross-system transaction spanning Google Sheets and PostgreSQL, nor
an exclusive lock against spreadsheet editors. The engine rechecks identity
anchors before writing and reconciles provider state on retry. Avoid concurrent
structural edits during a run. See Google's
[batch update contract](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate)
and [developer metadata guide](https://developers.google.com/workspace/sheets/api/guides/metadata).

On PostgreSQL, a destination-scoped transaction lock also serializes different
events targeting the same worksheet. The second event then sees the first event's
ownership metadata and stops instead of overwriting it. SQLite development uses
its database write serialization; concurrency regression tests run on PostgreSQL.

## Schedule sync (Sheets → Django)

**Service:** `src/apps/event/services/schedule_sync/`

Imports track assignments and project data from a Google Sheet into the database. Each
`CurrentProjectSchedule` row (typically one per event year, e.g. "Innovate to Grow 2025",
"Innovate to Grow 2026") carries **its own** sheet id and worksheet GIDs, and every row can be
synced independently — not only the one marked **Active**.

### Flow

1. A sync is triggered for a specific `CurrentProjectSchedule` row:
   - Django admin → Events → Current Project and Schedule → **Pull Current Projects & Schedule** (syncs the
     *active* row), or the per-row / change-form **Sync from Google Sheets** action (syncs *that* row), or
   - `python manage.py sync_schedule` (cron; see [operations](operations.md#schedule-auto-sync)).
2. `fetch_schedule_sheet_records(config)` opens **that row's** `sheet_id` and reads the tracks and projects
   worksheets by `tracks_gid` / `projects_gid`
3. Parses rows into track and project records
4. Replaces that row's `CurrentProject`, `EventScheduleSection`, `EventScheduleTrack`, `EventScheduleSlot` and
   `EventAgendaItem` rows inside one transaction (other schedules are untouched)
5. Records grand winners on the schedule and writes a `ScheduleSyncLog` entry

### Sheet structure

The schedule sheet is expected to contain:
- Track assignments (room, track name)
- Project data (team name, project title, class code, presentation order)
- Timing information mapped to schedule sections

### `CurrentProjectSchedule` fields

| Field | Purpose |
|-------|---------|
| `name` | Event label shown to editors (include the year, e.g. "Innovate to Grow 2026") |
| `is_active` | The default schedule for `/schedule`, `/event/projects/` and the assistant; exactly one row |
| `sheet_id` | Google Sheets document ID for **this** schedule |
| `tracks_gid` / `projects_gid` | Worksheet GIDs for the tracks and projects tabs |
| `auto_sync_enabled` / `sync_interval_minutes` | Per-row cron settings honoured by `sync_schedule` |

These are configured per row in Django admin → Events → Current Project and Schedule. CMS pages pick which
schedule an embedded `/schedule` widget shows — see
[content management](../../cms-admin/content-management.md#embed-widget-blocks-and-schedule-selection).

## Past-projects sync (Sheets → Django)

**Service:** `src/apps/projects/services/sheet_sync/`

Imports the historical past-projects catalog from a Google Sheet into the `Project`/`Semester` tables that
back the public `/past-projects` page. This replaces the legacy Flask page, which fetched the sheet **in the
browser** using a hardcoded API key; the key now lives only in the backend service account.

### Flow

1. An admin clicks **Pull Past Projects** in Django admin (Projects → Past Projects Sheet), or
   `python manage.py sync_past_projects` runs on a schedule.
2. `fetch_past_project_records()` reads the configured worksheet (by **name**) from the configured spreadsheet.
3. Each row's `Year-Semester` cell is parsed by `resolve_project_row` into a `Semester` FK (auto-creating and
   publishing the semester); the other columns are mapped by header text to `Project` fields.
4. Rows with an unparseable/empty `Year-Semester`, an out-of-range season, a blank title, or a duplicate
   `(semester, class_code, team_number)` are skipped and counted.
5. In one transaction, **all `Project` rows with `source="sheet"` are deleted and recreated** from the sheet —
   a full replace. Rows with `source="manual"` (CSV-imported or hand-entered in admin) are **never touched**.
6. The `projects:past-all` cache is cleared (explicitly, since `bulk_create` does not fire `post_save`), and a
   `PastProjectSyncLog` row records the outcome.
7. `GET /projects/past-all/` serves the rows to the React `/past-projects` page.

### Visibility note (newest semester)

`GET /projects/past-all/` hides the **newest published semester** (treated as the in-flight "current" semester,
owned by the event flow via `CurrentProjectSchedule`). The past-projects sheet is historical and should not
contain the current event semester. Configure/publish the current event semester **before** relying on the
public page, otherwise the most recent synced semester would be hidden as "current".

### Config model fields (`PastProjectsSheetConfig`)

| Field | Purpose |
|-------|---------|
| `sheet_id` | Google Sheets document ID |
| `worksheet_name` | Worksheet/tab name (default `Past-Projects-WEB-LIVE`) |
| `auto_sync_enabled` / `sync_interval_minutes` | Cron auto-sync gate (`sync_is_due`) |
| `last_synced_at` / `sync_error` / `sync_count` | Last-run status |

## Error handling

The registration and schedule sync services:
- Check for valid `GoogleCredentialConfig` before attempting any API call
- Log errors to `RegistrationSheetSyncLog` (registration) or application logs (schedule)
- Preserve the user-facing registration while recording a durable follow-up
  job in the same transaction
- Retry only known-safe transient failures and retain failed job/log evidence
- Never advance a registration-sheet cursor on provider failure

Past-projects sync is **explicit**, not request-triggered, so it fails loud instead of open:
- It aborts with a `SheetSyncError` (and writes a FAILED `PastProjectSyncLog`) **before deleting anything**
  when the fetch is misconfigured or yields no importable rows — existing data is never replaced with nothing.
- The management command turns a `SheetSyncError` into a non-zero `CommandError` so cron/CI supervisors notice.

## Related pages

- [Operations](operations.md) — Setup and troubleshooting
- [API: Events](../../api/events.md) — Registration endpoint that triggers sync
- [Architecture: Integrations](../../architecture/integrations.md) — Overview of all integrations

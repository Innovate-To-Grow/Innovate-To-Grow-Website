# Google Sheets Data Flow

How data moves between the Django backend and Google Sheets.

## Registration sync (Django → Sheets)

**Service:** `src/apps/event/services/registration_sheet_sync/`

When a new event registration is created, the same database transaction
creates a deduplicated `BackgroundJob` outbox row. The ECS worker appends the
registration snapshot to the configured Google Sheet.

### Flow

1. `EventRegistrationCreateView` saves the registration
2. Creates the Sheets job in the registration transaction when durable jobs
   are enabled
3. A worker claims the job and locks the event row, serializing syncs per event
4. The worker captures a cutoff and selects the complete database snapshot
   through that cutoff
5. It reads existing stable registration UUIDs and appends only missing rows
6. It advances the audit cursor only after the write is confirmed

### Sheet columns

| Column | Source |
|--------|--------|
| Order | Sequential number |
| First Name | `attendee_first_name` |
| Last Name | `attendee_last_name` |
| Phone | `attendee_phone` (if collected) |
| When Started | Registration creation time |
| Last Updated | Registration update time |
| Membership Primary | `attendee_email` |
| Membership Secondary | `attendee_secondary_email` when enabled |
| Ticket Type | Ticket type name |
| Custom questions | Dynamic columns based on `Question` model |
| Registration ID | Stable registration UUID; final, application-managed, and protected |

### Durable idempotent append

`BackgroundJob` dedupe keys prevent duplicate queue records. The worker uses
the final `Registration ID` column to make provider retries idempotent. It
re-reads the full bounded snapshot on each run so a transaction that committed
after an earlier read cannot be skipped because of timestamp/cursor ordering.
`RegistrationSheetSyncLog` records the cursor range, selected IDs, written
count, status, and sanitized error.

### Full replace sync

A recovery mechanism that replaces all sheet data with current database records. Useful when:
- The sheet data has drifted from the database
- Rows were accidentally deleted from the sheet
- A bulk re-sync is needed after a data correction

Triggered via Django admin action on the Event model. A populated sheet with a
legacy or drifted header is duplicated before replacement; the exact new
header is written and the final `Registration ID` column is protected.

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

# Google Sheets Data Flow

How data moves between the Django backend and Google Sheets.

## Registration sync (Django → Sheets)

**Service:** `src/apps/event/services/registration_sheet_sync.py`

When a new event registration is created, the system appends a row to the configured Google Sheet.

### Flow

1. `EventRegistrationCreateView` saves the registration
2. Calls the registration sheet sync service
3. Service checks if the event has `registration_sheet_id` and `registration_sheet_gid` set
4. If configured, the registration is queued for batch append
5. After a 15-second debounce window, all queued registrations are appended in a single API call

### Sheet columns

| Column | Source |
|--------|--------|
| Order | Sequential number |
| First Name | `attendee_first_name` |
| Last Name | `attendee_last_name` |
| Phone | `attendee_phone` (if collected) |
| Timestamp | Registration creation time |
| Email | `attendee_email` |
| Ticket | Ticket type name |
| Custom questions | Dynamic columns based on `Question` model |

### Debounced batch append

To avoid hitting Google Sheets API rate limits, writes are debounced:

1. Registration triggers a sync request
2. If a batch window is already open (within 15 seconds), the registration is added to the pending batch
3. After 15 seconds of no new registrations, the batch is flushed as a single append operation
4. Each sync is logged in `RegistrationSheetSyncLog`

### Full replace sync

A recovery mechanism that replaces all sheet data with current database records. Useful when:
- The sheet data has drifted from the database
- Rows were accidentally deleted from the sheet
- A bulk re-sync is needed after a data correction

Triggered via Django admin action on the Event model.

## Schedule sync (Sheets → Django)

**Service:** `src/apps/event/services/schedule_sync.py`

Imports track assignments and project data from a Google Sheet into the database.

### Flow

1. Admin triggers schedule sync from the Django admin
2. Service reads the configured worksheet (by GID) from the event's spreadsheet
3. Parses rows into track and project records
4. Creates or updates `Semester`, `Project`, `EventScheduleTrack`, and `EventScheduleSlot` models
5. Supports grand winner tracking

### Sheet structure

The schedule sheet is expected to contain:
- Track assignments (room, track name)
- Project data (team name, project title, class code, presentation order)
- Timing information mapped to schedule sections

### Event model fields

| Field | Purpose |
|-------|---------|
| `registration_sheet_id` | Google Sheets document ID |
| `registration_sheet_gid` | Worksheet GID for registration data |

These are configured on the `Event` model in Django admin.

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
- Do not raise exceptions that would interrupt the user-facing request
- Fail open: if sync fails, the primary operation (registration creation, schedule display) still succeeds

Past-projects sync is **explicit**, not request-triggered, so it fails loud instead of open:
- It aborts with a `SheetSyncError` (and writes a FAILED `PastProjectSyncLog`) **before deleting anything**
  when the fetch is misconfigured or yields no importable rows — existing data is never replaced with nothing.
- The management command turns a `SheetSyncError` into a non-zero `CommandError` so cron/CI supervisors notice.

## Related pages

- [Operations](operations.md) — Setup and troubleshooting
- [API: Events](../../api/events.md) — Registration endpoint that triggers sync
- [Architecture: Integrations](../../architecture/integrations.md) — Overview of all integrations

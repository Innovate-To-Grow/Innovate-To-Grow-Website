# Google Sheets Data Flow

How data moves between the Django backend and Google Sheets.

## Registration sync (Django → Sheets)

**Service:** `src/event/services/registration_sheet_sync.py`

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

**Service:** `src/event/services/schedule_sync.py`

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

## Error handling

Both sync services:
- Check for valid `GoogleCredentialConfig` before attempting any API call
- Log errors to `RegistrationSheetSyncLog` (registration) or application logs (schedule)
- Do not raise exceptions that would interrupt the user-facing request
- Fail open: if sync fails, the primary operation (registration creation, schedule display) still succeeds

## Related pages

- [Operations](operations.md) — Setup and troubleshooting
- [API: Events](../../api/events.md) — Registration endpoint that triggers sync
- [Architecture: Integrations](../../architecture/integrations.md) — Overview of all integrations

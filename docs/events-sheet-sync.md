# Google Sheets Integration

The ITG website integrates with Google Sheets in two ways:

1. **Display proxy** — The frontend reads sheet data via `/sheets/<slug>/` and renders it directly (event schedules, team assignments, project tables). The backend fetches, parses, and caches the data but does not write it to the database.

2. **Database import** — The `sync_projects` management command reads sheet data and creates/updates Semester and Project records in the database.

Both paths are read-only. The application never writes back to Google Sheets.

## Configuration

### Authentication

Two authentication methods are supported, configured via environment variables:

**Service account (recommended for production):**
```
GOOGLE_SHEETS_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"...","client_email":"..."}
GOOGLE_SHEETS_SCOPES=https://www.googleapis.com/auth/spreadsheets.readonly
```

The service account email must be granted read access to each spreadsheet (via the sheet's share settings).

**API key (simpler, for development):**
```
GOOGLE_SHEETS_API_KEY=your-api-key
```

Only works with publicly shared spreadsheets. No authentication scoping.

The backend auto-detects which method to use: service account credentials take precedence; if absent, it falls back to the API key. If neither is set, sheet requests return a 502 error.

**Implementation:** `src/core/services/google_sheets.py`

### GoogleSheetSource Model

Sheet connections are configured in the Django admin under **Site Settings > Sheet Sources**. Each source maps a slug to a spreadsheet range.

| Field | Purpose |
|-------|---------|
| `slug` | URL identifier (e.g., `current-event`) — used in `/sheets/<slug>/` |
| `title` | Display name |
| `sheet_type` | One of: `current-event`, `past-projects`, `archive-event` |
| `spreadsheet_id` | Google Sheets document ID (from the URL) |
| `range_a1` | Cell range in A1 notation (e.g., `Sheet1!A1:L100`) |
| `tracks_spreadsheet_id` | Optional separate spreadsheet for track metadata |
| `tracks_sheet_name` | Sheet name within the tracks spreadsheet |
| `semester_filter` | Optional filter string (e.g., `2025-1 Spring`) to limit rows |
| `cache_ttl_seconds` | How long to cache fresh data (default: 300) |
| `is_active` | Whether this source is available |

**Model:** `src/pages/models/pages/layout/google_sheet_source.py`

---

## Display Proxy Path

### How It Works

1. Frontend requests `GET /sheets/<slug>/`
2. Backend looks up the `GoogleSheetSource` by slug
3. Backend checks the cache for fresh data
4. If cache miss or stale, fetches from Google Sheets API
5. Parses raw cell values into structured rows
6. Returns JSON response to frontend

### Column Layouts

The parser expects specific column layouts depending on the `sheet_type`:

**`current-event` and `archive-event` (12 columns):**

| Col | Header |
|-----|--------|
| A | Track |
| B | Order |
| C | Year-Semester (e.g., `2025-1 Spring`) |
| D | Class |
| E | Team# |
| F | TeamName |
| G | Project Title |
| H | Organization |
| I | Industry |
| J | Abstract |
| K | Student Names |
| L | NameTitle |

**`past-projects` (9 columns):**

| Col | Header |
|-----|--------|
| A | Year-Semester |
| B | Class |
| C | Team# |
| D | TeamName |
| E | Project Title |
| F | Organization |
| G | Industry |
| H | Abstract |
| I | Student Names |

**Track info sheet (3 columns):**

| Col | Header |
|-----|--------|
| A | name |
| B | room |
| C | zoomLink |

### Response Shape

```json
{
  "slug": "current-event",
  "title": "Spring 2025 Event",
  "sheet_type": "current-event",
  "rows": [
    {
      "Track": "1",
      "Order": "1",
      "Year-Semester": "2025-1 Spring",
      "Class": "ENGR 120",
      "Team#": "3",
      "TeamName": "InnoTech",
      "Project Title": "Smart Campus Wayfinding",
      "Organization": "UC Merced",
      "Industry": "Education",
      "Abstract": "A mobile app that...",
      "Student Names": "Alice, Bob, Charlie",
      "NameTitle": ""
    }
  ],
  "track_infos": [
    {"name": "Track 1", "room": "COB2 130", "zoomLink": ""}
  ]
}
```

### Caching Strategy

The display proxy uses **stale-while-revalidate** caching:

| Scenario | Behavior |
|----------|----------|
| Fresh cache hit (within TTL) | Return cached data immediately |
| Stale cache hit (within 6x TTL) | Return stale data, trigger background refresh in a daemon thread |
| Full cache miss | Synchronous fetch from Google Sheets API |

Cache keys:
- `sheets:<slug>:data` — fresh data (TTL from `cache_ttl_seconds`)
- `sheets:<slug>:stale` — stale fallback (TTL = 6x fresh TTL)

Cache is automatically invalidated when a `GoogleSheetSource` is saved or deleted (via signal handler in `src/pages/signals.py`). Admins can also force-refresh via `POST /sheets/<slug>/refresh/` (requires admin authentication).

**Implementation:** `src/pages/services/google_sheets.py`, `src/pages/views/sheets.py`

---

## Database Import Path

### sync_projects Command

The `sync_projects` management command reads Google Sheets data and creates/updates Semester and Project database records.

```bash
# Sync all active sheet sources
python manage.py sync_projects

# Sync a specific source by slug
python manage.py sync_projects --slug current-event

# Direct sync with explicit parameters
python manage.py sync_projects \
  --spreadsheet-id 1ABC... \
  --range "Sheet1!A1:L100" \
  --type current-event \
  --semester-filter "2025-1 Spring"
```

**Options:**

| Flag | Purpose |
|------|---------|
| `--slug SLUG` | Sync a specific `GoogleSheetSource` by its slug |
| `--spreadsheet-id ID` | Spreadsheet document ID (for direct sync) |
| `--range RANGE` | A1 range notation (for direct sync) |
| `--type TYPE` | Sheet type: `current-event`, `past-projects`, or `archive-event` |
| `--semester-filter FILTER` | Filter rows by Year-Semester value |

### How Import Works

1. Fetches raw values from Google Sheets API
2. Parses the Year-Semester column (e.g., `2025-1 Spring`) into year and season
3. Creates or retrieves the Semester record (auto-published on creation)
4. For each data row, creates or updates a Project record matched by semester + class_code + team_number
5. Clears the `projects:current` and `projects:past-all` cache keys

### Row-to-Model Mapping

| Sheet Column | Project Field |
|-------------|---------------|
| Class | `class_code` |
| Team# | `team_number` |
| TeamName | `team_name` |
| Project Title | `project_title` |
| Organization | `organization` |
| Industry | `industry` |
| Abstract | `abstract` |
| Student Names | `student_names` |
| Track | `track` (integer, current-event/archive-event only) |
| Order | `presentation_order` (integer, current-event/archive-event only) |

Rows with empty Project Title are skipped.

**Implementation:** `src/projects/services/sync_sheets.py`, `src/projects/management/commands/sync_projects.py`

---

## Failure Modes and Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| 502 on `/sheets/<slug>/` | No credentials configured | Set `GOOGLE_SHEETS_CREDENTIALS_JSON` or `GOOGLE_SHEETS_API_KEY` |
| 502 with "HttpError" | Spreadsheet not shared with service account | Share the spreadsheet with the service account email |
| Empty rows returned | Wrong `range_a1` or sheet name | Verify the range in the GoogleSheetSource admin |
| Stale data persists | Cache not invalidating | Use `POST /sheets/<slug>/refresh/` or save the GoogleSheetSource in admin |
| `sync_projects` creates duplicates | Year-Semester format mismatch | Ensure format is exactly `YYYY-N Season` (e.g., `2025-1 Spring`) |
| `sync_projects` skips rows | Empty Project Title column | Fill in the Project Title for all data rows |
| API key doesn't work | Spreadsheet is not publicly shared | Either share publicly or switch to service account credentials |
| "GoogleSheetsConfigError" | Neither credential method is configured | Set at least one of the two env var options |

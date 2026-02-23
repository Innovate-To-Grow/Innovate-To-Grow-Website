# Events Google Sheets Sync API

Bidirectional sync between the I2G event database and Google Sheets. The **import** endpoint writes sheet data into the database; the **export** endpoint reads database data for the sheet to consume.

Both endpoints require API key authentication via the `X-API-Key` header.

## Authentication

All sync endpoints use API key authentication:

```
X-API-Key: <your-api-key>
```

The API key is validated by `events.authentication.APIKeyAuthentication` and `APIKeyPermission`.

---

## Import: Sheets to Database

### `POST /events/sync/`

Imports event data from a Google Sheets payload into the database. The operation runs inside an **atomic transaction** — if any part fails, the entire import is rolled back.

### Payload Structure

The request body is a JSON object with optional top-level keys. Only the keys present in the payload are processed; omitted sections are left unchanged.

```json
{
  "basic_info": { ... },
  "schedule": [ ... ],
  "winners": { ... },
  "expo_table": [ ... ],
  "reception_table": [ ... ]
}
```

### Sections

#### `basic_info` — Event Metadata

Updates (or creates) the event's basic information.

```json
{
  "basic_info": {
    "event_name": "I2G Innovation Showcase 2025",
    "event_date": "2025-04-15",
    "event_time": "09:00:00",
    "upper_bullet_points": ["Point 1", "Point 2"],
    "lower_bullet_points": ["Point A", "Point B"]
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_name` | string | Yes | Event display name |
| `event_date` | string (YYYY-MM-DD) | Yes | Event date |
| `event_time` | string (HH:MM:SS) | Yes | Event start time |
| `upper_bullet_points` | string[] | No | Upper section bullet points |
| `lower_bullet_points` | string[] | No | Lower section bullet points |

Date and time are combined into a timezone-aware datetime using the server's configured timezone (`America/Los_Angeles`).

If no event exists in the database and `basic_info` is not provided, the request returns `400`.

#### `schedule` — Programs, Tracks, and Presentations

Performs a **full replace** of the event schedule. All existing programs, tracks, and presentations are deleted before the new data is inserted.

```json
{
  "schedule": [
    {
      "program_name": "Morning Session",
      "tracks": [
        {
          "track_name": "Track A",
          "room": "Room 101",
          "start_time": "09:00:00",
          "presentations": [
            {
              "order": 1,
              "team_id": "T001",
              "team_name": "Team Alpha",
              "project_title": "AI for Good",
              "organization": "UC Merced"
            },
            {
              "order": 2,
              "project_title": "Break",
              "team_id": null,
              "team_name": null,
              "organization": null
            }
          ]
        }
      ]
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `program_name` | string | Yes | Program/session name |
| `tracks[].track_name` | string | Yes | Track name |
| `tracks[].room` | string | Yes | Room location |
| `tracks[].start_time` | string | No | Track start time |
| `tracks[].presentations[].order` | int | Yes | Display order |
| `tracks[].presentations[].team_id` | string | No | Team identifier (null for breaks) |
| `tracks[].presentations[].team_name` | string | No | Team name (null for breaks) |
| `tracks[].presentations[].project_title` | string | Yes | Presentation or break title |
| `tracks[].presentations[].organization` | string | No | Organization name |

#### `winners` — Track Winners and Special Awards

Performs a **full replace** of all winners data.

```json
{
  "winners": {
    "track_winners": [
      {
        "track_name": "Track A",
        "winner_name": "Team Alpha"
      }
    ],
    "special_awards": [
      {
        "program_name": "Innovation Award",
        "award_winner": "Team Beta"
      }
    ]
  }
}
```

#### `expo_table` / `reception_table` — Event Tables

Updates the expo or reception schedule tables stored as JSON on the Event model.

```json
{
  "expo_table": [
    { "time": "Room:", "description": "Ballroom A" },
    { "time": "2025-04-15T09:00:00Z", "description": "Setup begins" },
    { "time": "10:00", "description": "Doors open" }
  ]
}
```

**Time parsing logic:**
- Rows with `time: "Room:"` are treated as header rows; the `description` becomes the room name for subsequent rows.
- ISO-8601 datetime strings and strings containing `GMT` are parsed and reformatted to `H:MM AM/PM`.
- Plain `HH:MM` times without AM/PM get AM/PM appended based on the hour value.
- Rows missing both `time` and `description` are skipped.

### Success Response

**`200 OK`**:
```json
{
  "status": "success",
  "message": "Event data synced successfully.",
  "event_uuid": "uuid-string"
}
```

### Error Responses

| Code | Condition |
|------|-----------|
| `400` | Validation errors or no event exists and `basic_info` not provided |
| `401` | Missing or invalid API key |
| `403` | API key lacks permission |
| `500` | Server error (transaction rolled back) |

---

## Export: Database to Sheets

### `GET /events/sync/export/`

Exports the current live event data in a format suitable for Google Sheets consumption.

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | string | `full` | `full` returns all data; `delta` returns data only if changed since `since` |
| `since` | ISO-8601 datetime | — | Required when `mode=delta`. Watermark from previous export. |

### Full Mode

Returns the complete event data regardless of when it was last modified.

```
GET /events/sync/export/?mode=full
```

### Delta Mode

Compares the event's `updated_at` watermark against the provided `since` timestamp. If the event has been modified since that time, the full data is returned. If not, a minimal response indicates no changes.

```
GET /events/sync/export/?mode=delta&since=2025-04-15T12:00:00Z
```

**Watermark pattern**: The response includes a `watermark` field containing the event's `updated_at` timestamp. Clients should store this value and pass it as the `since` parameter on the next delta request.

### Response Structure

```json
{
  "mode": "full",
  "delta_changed": true,
  "generated_at": "2025-04-15T12:30:00Z",
  "watermark": "2025-04-15T12:25:00Z",
  "event": {
    "event_name": "...",
    "event_date_time": "...",
    "programs": [ ... ],
    "track_winners": [ ... ],
    "special_award_winners": [ ... ],
    "expo_table": [ ... ],
    "reception_table": [ ... ]
  }
}
```

When `delta_changed` is `false` (delta mode, no changes), the `event` field contains minimal data.

### Error Responses

| Code | Condition |
|------|-----------|
| `400` | Invalid `mode` value or missing `since` for delta mode |
| `401` | Missing or invalid API key |
| `404` | No live event found |

---

## Time Parsing Reference

The import endpoint handles multiple time formats from Google Sheets:

| Input Format | Parsed As |
|-------------|-----------|
| `2025-04-15T09:00:00Z` | `9:00 AM` |
| `2025-04-15T14:30:00Z` | `2:30 PM` |
| `Thu Apr 15 2025 09:00:00 GMT-0700` | `9:00 AM` |
| `09:00` (no AM/PM) | `9:00 AM` |
| `14:30` (no AM/PM) | `2:30 PM` |
| `10:00 AM` (already formatted) | `10:00 AM` (unchanged) |
| `Room:` | Treated as header row, not a time |

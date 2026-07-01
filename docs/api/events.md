# Events API

Event registration, ticketing, schedule, and check-in endpoints. All under `/event/`.

## Overview

The event system manages the Innovate To Grow showcase event lifecycle: registration with custom questions, ticket generation with barcodes, schedule display, and day-of check-in scanning. `Event.is_live` still identifies the single featured/current event, while `Event.registration_open` controls which events currently accept public registration. Multiple events can have `registration_open=true` at the same time.

## Code locations

| Concern | Path |
|---------|------|
| Views | `src/apps/event/views/` |
| Serializers | `src/apps/event/serializers/` |
| Services | `src/apps/event/services/` |
| Models | `src/apps/event/models/` |
| URLs | `src/apps/event/urls.py` |

## Key models

| Model | Purpose |
|-------|---------|
| `Event` | Event configuration (name, slug, date, location, registration settings) |
| `EventRegistration` | One registration per member per event, with ticket code and custom answers |
| `Ticket` | Ticket types (free, paid, VIP, etc.) |
| `Question` | Custom registration form questions (stored as JSON answers) |
| `CheckIn` | Check-in configuration for an event |
| `CheckInRecord` | Individual check-in records linked to registrations |
| `CurrentProjectSchedule` | Schedule configuration (links to event and semester) |
| `EventScheduleSection` | Time blocks within the schedule |
| `EventScheduleTrack` | Parallel presentation tracks (by room) |
| `EventScheduleSlot` | Individual presentation or break slots |
| `EventAgendaItem` | Agenda items (keynotes, networking, etc.) |

## Endpoints

### Registration

#### `GET /event/registration-options/`

Returns one open event's registration form structure: available ticket types, custom questions, and event configuration (whether to collect secondary email, phone, etc.).

**Query parameters:**
- `event_slug` — preferred event selector.
- `event` — legacy alias for `event_slug`.

When no event slug is provided, legacy behavior is preserved only if exactly one event is open for registration. If multiple events are open, the endpoint returns `400` with `detail: "Please choose an event."` and an `events` list.

**Permission:** AllowAny

#### `GET /event/registration-events/`

Returns all events with `registration_open=true`, sorted by date then name. If the request includes a valid authenticated user, each event includes that user's existing registration for the event, or `null`.

**Permission:** AllowAny

#### `POST /event/registrations/`

Creates an event registration for an event whose `registration_open=true`.

**Request:**
```json
{
  "event_slug": "demo-day",
  "ticket_id": "<ticket_id>",
  "attendee_first_name": "Jane",
  "attendee_last_name": "Doe",
  "attendee_organization": "Example Co",
  "attendee_secondary_email": null,
  "attendee_phone": null,
  "attendee_phone_region": null,
  "answers": [
    {"question_id": "<uuid>", "answer": "Computer Science"}
  ]
}
```

**Behavior:**
- Generates a unique ticket code (`I2G-{random}`)
- Sends ticket confirmation email with barcode
- Syncs registration to Google Sheets (debounced, 15-second batch)
- One registration per member per event (unique constraint)
- The same member can register once for each different open event

**Barcode format:** `I2G|EVENT|{event_slug}|{ticket_code}`

### Tickets

#### `GET /event/my-tickets/`

Returns the authenticated user's event registrations with ticket details.

**Permission:** Authenticated

Ticket confirmation emails no longer use a dedicated `/event/ticket-login/` endpoint. They embed a unified login link (`/login-link?token=...`, validated by `POST /mail/login-link/`) whose validity and reuse policy come from the event (`ticket_login_validity_days`, `ticket_login_reusable`) and which redirects to `/event-registration?event=<event-slug>` after login. See [auth-and-mail.md](auth-and-mail.md).

### Schedule

#### `GET /event/schedule/`

Returns the current event's full schedule: sections (time blocks), tracks (rooms), slots (presentations), and agenda items.

**Permission:** AllowAny

**Response structure:**
```json
{
  "event": { ... },
  "sections": [
    {
      "title": "Morning Session",
      "start_time": "09:00",
      "end_time": "12:00",
      "tracks": [
        {
          "name": "Track A - Room 101",
          "slots": [
            {
              "project": { "team_name": "...", "project_title": "..." },
              "start_time": "09:00",
              "duration_minutes": 15
            }
          ]
        }
      ]
    }
  ],
  "agenda": [...]
}
```

#### `GET /event/projects/`

Returns the current event with associated projects (linked via `CurrentProjectSchedule` → `Semester`).

**Permission:** AllowAny

### Check-in

#### `POST /event/check-in/scan/`

Scans a barcode/QR code to check in a registrant.

**Permission:** Staff only

#### `GET /event/check-in/status/`

Returns check-in statistics for the current event.

**Permission:** Staff only

### Phone verification

Used when the event requires phone collection with verification.

#### `POST /event/send-phone-code/`

Sends an SMS verification code via AWS SNS.

#### `POST /event/verify-phone-code/`

Verifies the SMS code.

## Google Sheets sync

Event registrations can be synced to a Google Sheet configured on the `Event` model:
- `registration_sheet_id` — Google Sheets document ID
- `registration_sheet_gid` — Specific worksheet GID

The sync is debounced (15-second batch window) to avoid API rate limits. See [Google Sheets Integration](../integrations/google-sheets/index.md) for details.

## Related pages

- [Auth & Mail](auth-and-mail.md) — Ticket auto-login and email challenges
- [Projects](projects.md) — Project data displayed in schedule
- [CMS & Admin: Operations](../cms-admin/operations.md) — Event admin operations
- [Google Sheets Integration](../integrations/google-sheets/index.md) — Registration sync details

# Events API

Event registration, ticketing, schedule, and check-in endpoints. All under `/event/`.

## Overview

The event system manages the Innovate To Grow showcase event lifecycle: registration with custom questions, ticket generation with barcodes, schedule display, and day-of check-in scanning. `Event.registration_open` is the sole event-registration availability flag, and multiple events can have it enabled at the same time. Schedule and current-project selection remain configured separately through `CurrentProjectSchedule`.

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
| `Event` | Event configuration (name, slug, inclusive start/end dates, location, registration settings) |
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

Event-bearing registration and ticket responses expose `date` as the inclusive start date and `end_date` as the inclusive end date. For a single-day event the values are equal. Calendar downloads convert the inclusive end date to the next day when emitting the exclusive end required for an all-day calendar event.

## Endpoints

### Registration

#### `GET /event/registration-options/`

Returns one open event's registration form structure: available ticket types, custom questions, the event date range, and form configuration (whether to prompt for secondary email or a phone number, and whether phone verification is required).

**Query parameters:**
- `event_slug` — preferred event selector.
- `event` — legacy alias for `event_slug`.

When no event slug is provided, legacy behavior is preserved only if exactly one event is open for registration. If multiple events are open, the endpoint returns `400` with `detail: "Please choose an event."` and an `events` list.

**Permission:** AllowAny

#### `GET /event/registration-events/`

Returns all events with `registration_open=true`, sorted by start date then name. Each event includes `date` and `end_date`. If the request includes a valid authenticated user, each event also includes that user's existing registration for the event, or `null`.

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
  "answers": [
    {"question_id": "<uuid>", "answer": "Computer Science"}
  ]
}
```

**Behavior:**
- Generates a unique ticket code (`I2G-{random}`)
- Creates durable ticket-email and registration-Sheets jobs in the same
  database transaction as the registration
- The worker sends the barcode email and idempotently syncs the bounded
  registration snapshot to Google Sheets
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

Returns the selected `CurrentProjectSchedule` (or the active/default schedule when no `schedule_id` is supplied): sections (time blocks), tracks (rooms), slots (presentations), and agenda items.

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

Used when **Prompt for Phone Number** and phone verification are both enabled for the event.

#### `POST /event/send-phone-code/`

Creates and sends a durable SMS verification challenge. Returns
`challenge_id`; the challenge is bound to the event-registration purpose and
event context. New clients send
`{ "phone": "...", "region": "1-US", "event_slug": "<event>" }`.

#### `POST /event/verify-phone-code/`

Verifies `{ "phone", "code", "challenge_id", "event_slug" }` and moves the
event-bound grant to `VERIFIED`. Registration submits
`phone_verification_challenge_id`; its transaction performs the one-time
`VERIFIED → CONSUMED` transition, so a failed registration does not burn the
proof.

For the one-release compatibility window ending no earlier than 2026-10-23,
`event_slug` may be omitted only when exactly one open event requires phone
verification; the server binds the challenge to that unambiguous event.
Verification without `challenge_id` may likewise resolve the newest matching
challenge. New clients must send both fields.

## Google Sheets sync

Event registrations can be synced to a Google Sheet configured on the `Event` model:
- `registration_sheet_id` — Google Sheets document ID
- `registration_sheet_gid` — Specific worksheet GID

The PostgreSQL outbox worker serializes syncs per event, captures a cutoff,
deduplicates by the final protected `Registration ID` column, and advances the
cursor only after a confirmed write. See
[Google Sheets Integration](../integrations/google-sheets/index.md) for
details.

## Related pages

- [Auth & Mail](auth-and-mail.md) — Ticket auto-login and email challenges
- [Projects](projects.md) — Project data displayed in schedule
- [CMS & Admin: Operations](../cms-admin/operations.md) — Event admin operations
- [Google Sheets Integration](../integrations/google-sheets/index.md) — Registration sync details

# Events API

Event registration, ticketing, schedule, and check-in endpoints. All under `/event/`.

## Overview

The event system manages the Innovate To Grow showcase event lifecycle: registration with custom questions, ticket generation with barcodes, schedule display, and day-of check-in scanning.

## Code locations

| Concern | Path |
|---------|------|
| Views | `src/event/views/` |
| Serializers | `src/event/serializers/` |
| Services | `src/event/services/` |
| Models | `src/event/models/` |
| URLs | `src/event/urls.py` |

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

Returns the current live event's registration form structure: available ticket types, custom questions, and event configuration (whether to collect secondary email, phone, etc.).

**Permission:** AllowAny

#### `POST /event/registrations/`

Creates an event registration.

**Request:**
```json
{
  "event": "<event_id>",
  "ticket": "<ticket_id>",
  "attendee_first_name": "Jane",
  "attendee_last_name": "Doe",
  "attendee_email": "jane@example.com",
  "attendee_secondary_email": null,
  "attendee_phone": null,
  "question_answers": [
    {"question_id": "<uuid>", "answer": "Computer Science"}
  ]
}
```

**Behavior:**
- Generates a unique ticket code (`I2G-{random}`)
- Sends ticket confirmation email with barcode
- Syncs registration to Google Sheets (debounced, 15-second batch)
- One registration per member per event (unique constraint)

**Barcode format:** `I2G|EVENT|{event_slug}|{ticket_code}`

### Tickets

#### `GET /event/my-tickets/`

Returns the authenticated user's event registrations with ticket details.

**Permission:** Authenticated

#### `POST /event/ticket-login/`

Auto-login using a ticket token (from QR code scan).

**Request:** `{ "token": "<ticket_token>" }`

**Response:** JWT access/refresh tokens

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

Sends an SMS verification code via Twilio Verify.

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

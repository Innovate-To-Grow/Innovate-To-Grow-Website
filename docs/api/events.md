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

Returns one open event's registration form structure: available ticket types, custom questions, the event date range, and independent contact collection, verification, and requiredness settings.

| Contact | Collect | Verify if provided | Required |
|---------|---------|--------------------|----------|
| Phone number | `collect_phone` | `verify_phone` | `require_phone` |
| Secondary email | `allow_secondary_email` | `verify_secondary_email` | `require_secondary_email` |

Verification and requiredness can only be enabled when collection is enabled. With collection enabled, an optional contact may be left blank even when verification is enabled. A supplied contact must have a valid format and, when verification is enabled, a valid verification proof. Requiredness alone does not require verification. Secondary email must differ from the member's primary email, ignoring case.

Authenticated responses retain `member_emails` and `member_phone`, and add `member_secondary_email`: either `null` or `{ "email_address": "personal@example.com", "verified": true }`. `member_primary_email` identifies the actual primary email, or an empty string when none exists; the first item in `member_emails` is not necessarily a primary email. Profile contacts are explicit form prefills; submitting a blank optional contact does not silently refill it from the account. The server independently checks account contact ownership and verification on submission.

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
  "attendee_secondary_email": "personal@example.com",
  "secondary_email_verification_challenge_id": "<uuid>",
  "secondary_email_verification_token": "<short-lived-token>",
  "attendee_phone": "",
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
- Optional contact fields may be omitted or set to an empty string. Collected values are validated against the selected event's current settings.
- A member's own matching verified account contact can be reused without another code. Otherwise secondary-email verification requires both its challenge ID and verification token; phone verification uses `phone_verification_challenge_id`.
- Verification proofs are bound to the member, event, purpose, and normalized contact. Proof consumption, registration, account synchronization, and durable delivery jobs commit atomically; failure rolls them back together.
- Contact synchronization preserves trusted verification and never transfers a contact owned by someone else. Sending or checking a registration code does not create or update account contacts.
- Registration responses include `phone_verified` and `secondary_email_verified`; they never return submitted verification tokens.
- Missing, expired, or invalid required proofs return `400` with a descriptive `detail` and `code` of `phone_verification_required` or `secondary_email_verification_required`. Clients clear that contact's stale verification state and allow a new code request without clearing its value.

**Barcode format:** `I2G|EVENT|{event_slug}|{ticket_code}`

#### `POST /event/send-secondary-email-code/`

**Permission:** Authenticated

Request: `{ "event_slug": "demo-day", "email": "personal@example.com" }`, together with the shared send-verification proof fields for operation `event.send_secondary_email_code`. The event must be open and have both secondary-email collection and verification enabled.

Returns `email` and `challenge_id` through the standard guarded-send response. The frontend uses `withVerifiedSend` for preflight, idempotency, and retry handling. Existing email delivery, resend cooldown, destination quotas, and per-member limits apply.

#### `POST /event/verify-secondary-email-code/`

**Permission:** Authenticated

Request: `{ "event_slug": "demo-day", "email": "personal@example.com", "challenge_id": "<uuid>", "code": "123456" }`.

Success returns `{ "email": "personal@example.com", "verified": true, "challenge_id": "<uuid>", "verification_token": "<short-lived-token>" }` plus a descriptive `detail`. Submit the challenge ID and token with registration. Editing the email or switching events invalidates the frontend's stored proof. Codes and tokens expire and cannot be replayed.

### Contact settings migration

Existing events initialize `require_phone` from their previous `verify_phone` value, preserving required phone entry. Secondary email remains optional and unverified by default. New events default all contact settings to false; existing registrations are not retroactively marked email-verified.

The additive migrations retain database defaults for old-version inserts and preserve the earlier event schema's deferred compatibility columns. During a future mixed-version rollout, contact settings must be edited through the new admin: an older admin cannot clear the new required flags, and conflicting edits are rejected atomically by database constraints. This change does not deploy or modify any production event settings by itself.

### Tickets

#### `GET /event/my-tickets/`

Returns the authenticated user's event registrations with ticket details.

**Permission:** Authenticated

Ticket confirmation emails no longer use a dedicated `/event/ticket-login/` endpoint. They embed a unified login link (`/login-link?token=...`, validated by `POST /mail/login-link/`) whose validity and reuse policy come from the event (`ticket_login_validity_days`, `ticket_login_reusable`) and which redirects to `/event-registration?event=<event-slug>` after login. See [auth-and-mail.md](auth-and-mail.md).

### Schedule

#### `GET /event/schedule/`

Returns the selected `CurrentProjectSchedule` (or the active/default schedule when no `schedule_id` is supplied): sections (time blocks), tracks (rooms), slots (presentations), and agenda items.

**Query parameters:** `schedule_id` (optional UUID) — any `CurrentProjectSchedule` row, active or not (e.g. a previous year). An unknown id returns `404 {"detail": "No schedule configured."}`; a schedule that has never been synced returns `404 {"detail": "No schedule available."}`. CMS embed widgets and their page blocks use this to show different years side by side.

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

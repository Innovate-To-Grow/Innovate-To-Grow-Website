# Event Legacy Parity Plan

Date: 2026-02-11

## Goal

Bring old deployed event registration capabilities (`/membership/events*`) into the new DB-primary architecture, while keeping Google Sheet sync export in pull mode.

## Old vs New Mapping (Current)

### Implemented in this phase

1. Legacy route compatibility (browser pages + API status):
   - `GET/POST /membership/events` (server-rendered page)
   - `GET/POST /membership/events/<event_slug>` (server-rendered page)
   - `GET /membership/event-registration/<event_slug>/<token>` (server-rendered page)
   - `GET /membership/otp` and `GET /membership/otp/<token>` (server-rendered page)
   - `GET /membership/event-registration/status/<event_slug>/<token>` (JSON status API)
2. DB-primary registration domain:
   - ticket options
   - event questions
   - registration records
   - registration answers
3. Registration API flow:
   - request link
   - fetch form schema + existing snapshot
   - submit registration (full replace answers)
   - optional SMS OTP
   - OTP verify + status query
4. Admin coverage for event registration models.
5. Automated test coverage for registration APIs and membership page routes.

### Remaining gaps to reach full old behavior parity

1. Old “unknown email -> send complete membership registration email” behavior is not ported.
   - current behavior: `member_not_found` (404) in request-link flow.
2. Old primary/secondary email verification branching logic is not ported 1:1.
3. Old member “custom dynamic fields” (`edit_form`) are not ported to authn/event APIs.
4. Old confirmation email variants and SMS message templates are simplified and not 1:1 matched.
5. Receipt-style HTML result pages are simplified; the new pages currently show inline success messages.

## Next Phases (Decision-Complete)

### Phase A: UX parity wrapper (HTML or SPA route adapter)

1. Build membership event pages that call current APIs:
   - email entry
   - token-based registration form
   - OTP verify page
   - success/failure pages
2. Keep existing API endpoints as backend contract, avoid logic duplication.

Acceptance:
- old external links can be opened by browser users and complete registration end-to-end without raw JSON.

### Phase B: Membership bootstrap parity

1. Define “member not found” behavior:
   - option A: create pending member profile + send registration link automatically
   - option B: keep strict 404 and show guided signup page
2. Implement selected behavior with notify templates and rate limiting.

Acceptance:
- unknown email flow is explicitly supported and test-covered.

### Phase C: Contact verification parity

1. Add explicit primary/secondary email verification state transitions in authn.
2. Align event registration email dispatch with verification states.
3. Add regression tests for verification matrix.

Acceptance:
- verified/unverified branch behavior is deterministic and documented.

### Phase D: Dynamic custom fields parity

1. Introduce DB schema for dynamic member custom fields (if still required by product).
2. Expose those fields in registration form payload and submit APIs.
3. Migrate old data mapping rules.

Acceptance:
- old dynamic field use-cases can be configured and persisted in new system.

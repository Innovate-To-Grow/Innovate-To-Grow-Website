# Event Legacy Parity Plan

Date: 2026-02-11

## Goal

Bring old deployed event registration capabilities (`/membership/events*`) into the new DB-primary architecture, while keeping Google Sheet sync export in pull mode.

## Old vs New Mapping (Current)

### Implemented in this phase

1. Legacy route compatibility (API form):
   - `GET/POST /membership/events`
   - `GET/POST /membership/events/<event_slug>`
   - `GET/POST /membership/event-registration/<event_slug>/<token>`
   - `POST /membership/otp`
   - `POST /membership/otp/<token>`
   - `GET /membership/event-registration/status/<event_slug>/<token>`
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
5. Automated test coverage for registration + legacy route compatibility.

### Remaining gaps to reach full old behavior parity

1. Server-rendered HTML templates are not ported:
   - old pages under `project/templates/membership/events/*` were form pages and receipts.
   - new compatibility routes currently return JSON (API-first), not Jinja/HTML pages.
2. Old “unknown email -> send complete membership registration email” behavior is not ported.
   - current behavior: `member_not_found` (404) in request-link flow.
3. Old primary/secondary email verification branching logic is not ported 1:1.
4. Old member “custom dynamic fields” (`edit_form`) are not ported to authn/event APIs.
5. Old confirmation email variants and SMS message templates are simplified and not 1:1 matched.

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

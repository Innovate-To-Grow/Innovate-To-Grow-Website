# Self-hosted email and SMS send verification

This site protects every user-triggered verification-code send with a
self-hosted ALTCHA proof of work **and** server-side destination, account, and
SMS-budget controls. Proof of work raises the cost of automated requests. It
does not independently prove that a request came from a human.

The open-source ALTCHA widget (`altcha` 3.2.2) and Python library (`altcha`
2.1.0) run entirely on project-controlled infrastructure. There is no ALTCHA
Cloud, Sentinel, or third-party CAPTCHA runtime.

## What is protected

| Entry point | Operation |
|-------------|-----------|
| `POST /authn/email-auth/request-code/` | `email_auth.request_code` |
| `POST /authn/phone-auth/request-code/` | `phone_auth.request_code` |
| `POST /authn/login/request-code/` | `login.request_code` |
| `POST /authn/register/` | `register` |
| `POST /authn/register/resend-code/` | `register.resend_code` |
| `POST /authn/password-reset/request-code/` | `password_reset.request_code` |
| `POST /authn/change-password/request-code/` | `change_password.request_code` |
| `POST /authn/delete-account/request-code/` | `delete_account.request_code` |
| `POST /authn/contact-emails/` | `contact_email.create` |
| `POST /authn/contact-emails/<id>/request-verification/` | `contact_email.request_verification` |
| `POST /authn/contact-phones/<id>/request-verification/` | `contact_phone.request_verification` |
| `POST /event/send-phone-code/` | `event.send_phone_code` |
| Django admin login: initial email, remembered account, resend | `admin.login.*` |

Ordinary ticket, notification, campaign, and transactional email is unchanged.
`POST /authn/subscribe/` only stores a subscription; authentication on that page
uses the unified code flows above.

## Protocol

1. Client `POST /authn/send-verification/challenge/` with the operation and
   destination (never in a query string). Response is private (`Cache-Control:
   no-store`) and includes a signed ALTCHA challenge plus `challenge_id`.
   Admin forms instead use `POST /admin/send-verification/challenge/`, which
   accepts only admin operations and requires the form's CSRF token. This keeps
   the remembered-account cookie within its existing `/admin/` scope.
2. The browser solves the proof with a local worker (no CDN).
3. The send request includes `verification_challenge_id`, `verification_payload`,
   and a client-generated `send_request_id`. A new, explicit resend uses a new
   challenge and request id only after the previous attempt is resolved.
   Transport retries reuse the request id.
4. After authentication, one PostgreSQL transaction rechecks expiry/bindings,
   consumes the challenge once, reserves destination quotas, and inserts the
   send-request row. Delivery providers are called **after** commit.
5. `GET /authn/send-verification/requests/<request_id>/` returns that client's
   recorded state. Other users' ids 404-equivalent (`verification_invalid`).

Public authentication operations always bind to the browser session, even when
an access token is present. Account operations and authenticated event SMS bind
to the member; admin sends bind to the admin browser session. Challenge, send,
and status lookup use the same policy. Expired credentials on protected
operations return 401 before proof consumption. Use the same-site API proxy and
send session cookies; this change does not enable unrelated cross-site cookies.

The send context comes from validated business fields, not a client-selected
channel. Password reset accepts `identifier`, then the legacy `email` alias;
`destination` is a challenge convenience field and cannot override the send.
Password change and deletion reuse their validated recovery selection. Event
phone challenges use the sending endpoint's US-only normalization.

Idempotency compares the complete operation, channel, normalized recipient,
principal, and business fingerprint. The request is checked again after the
challenge lock; a unique-key conflict rolls back both consumption and quotas
before looking up the winning request. Only one `pending` to `sending` update
can claim dispatch. Neither time passing nor a lost response grants another
dispatch of a `sending` or `unknown` request.

Client error codes: `verification_required`, `verification_invalid`,
`verification_expired`, `verification_consumed`, `verification_context_mismatch`,
`verification_rate_limited`, `verification_unavailable`, `send_unknown`,
`send_throttled`, `send_request_conflict`, `send_paused`. Rate-limit responses
include `Retry-After`.

## Delivery outcomes and client recovery

Provider acceptance means that the provider accepted the request, not that the
message reached an inbox or handset. Explicit rejection/pre-dispatch failures
are definitely failed; a response lost after dispatch is unknown. Do not infer
this distinction from an HTTP status alone. Provider retries are disabled for
verification delivery; uncertain attempts retain both reservations and usable
OTP records until the OTP's normal expiry.

For ordinary sends, an uncertain first response or replay is HTTP 409 with
`code: send_unknown`, `request_id`, and `challenge_id` when applicable. The status
response includes `status`, `http_status`, `result`, and the same identifiers.
The frontend reconciles both that response and network errors before creating
any new request. It stores only unresolved request references/context hashes in
session storage, never a reusable proof. Reloads and repeated clicks query the
original request. Status-query failure remains unresolved, without automatic
resending; admin forms retain the equivalent reference in their session.

Password reset has a separate enumeration-safe public projection: eligible,
ineligible, accepted, failed, and uncertain delivery outcomes share a neutral
202 response and an opaque challenge ID. Its public status is `submitted`,
meaning the request was processed, not that delivery succeeded. Actual outcomes
remain internal, with reservations retained. This flow never automatically
resends either; a later explicit resend still requires a fresh proof and the
normal cooldown and budgets.

## Abuse limits

- Destination-wide (email or phone, all entry points): 60-second cooldown and 10
  reserved/accepted sends per rolling hour for email. SMS keeps the existing
  durable 10/hour reservation on `PhoneVerificationChallenge.send_reserved_at`
  so the hourly SMS counter is not double-charged.
- Existing member/purpose email caps and DRF per-view throttles remain.
- Channel-wide SMS daily reservation is required in `enforce` mode. Leave it
  unset until production traffic is measured; enforce then fails closed for SMS.
- Challenge issuance is rate-limited per real client IP (`NUM_PROXIES=1` behind
  the ALB). Campus users share IPs, so per-IP limits are not the sole control.
- A new anonymous session does not grant a fresh global sending budget.

Redis (when configured) is used only for early challenge throttles. PostgreSQL
is authoritative for single-use proofs, reservations, and request state. There
is no cross-store atomic transaction. Production without `REDIS_URL` falls back
to a **per-instance** file cache; multi-instance IP throttling is then not
guaranteed. Destination quotas still hold in PostgreSQL.

## Configuration

| Setting / Site Settings field | Local | Test | Production default |
|-------------------------------|-------|------|--------------------|
| `SEND_VERIFICATION_MODE` | `enforce` | `enforce` | `observe` until cutover |
| HMAC secrets | insecure local constants | test constants | **Send Verification** in Django admin |
| Cost | 500 | 10 | 5000 (env `SEND_VERIFICATION_COST`) |
| SMS daily limit | 1000 | 1000 | unset until calibrated |

Pause protected sends with mode `pause` (env or admin). Missing HMAC secrets or
required throttle/database failures fail closed in `enforce`.

For each policy field, an explicitly supplied setting/environment value wins,
then the active database configuration, then the documented default. Unset/None
means inherit. Local and CI settings are explicit overrides. An active admin
pause or an explicit environment pause always stops protected sends. The admin
shows the effective non-secret policy and each value's source; an environment
override must be removed before an admin edit to that field can take effect.

Invalid modes, algorithms, or numeric values return `verification_unavailable`
rather than falling back to observation or weaker limits. An explicit empty
HMAC value clears the setting; SMS daily limit 0 means uncalibrated and blocks
enforced SMS. Initial production defaults are cost 5000, challenge TTL 300s,
maximum proof size 8192 bytes, destination cooldown 60s, and email hourly cap 10.
Cost/hourly limits must be positive, TTL at least 30s, cooldown may be 0, and
the SMS cap must be positive before enforced SMS can run.

Rotate keys by copying current HMAC secrets into Previous, saving new current
values, and incrementing `key_version`. In-flight challenges verify against
current then previous signing keys and their stored issuance algorithm/cost,
so changing difficulty does not invalidate already-issued valid challenges.

Retention: pending challenges expire at five minutes; request rows are kept for
the 24-hour idempotency window plus `SEND_VERIFICATION_RETENTION_DAYS` (14)
by `python manage.py cleanup_send_verification`. Cleanup does not dispatch
messages or authorize a replay of a consumed/expired challenge.

## Deployment plan

1. Apply migrations and deploy backend with `SEND_VERIFICATION_MODE=observe`.
   Create an active Send Verification config and HMAC secrets. Do **not** send
   live email/SMS as part of this change.
2. Deploy frontend and admin assets that issue challenges and attach proofs.
   Keep compatible widget/worker files for rollback. Admin widget URLs must
   resolve through Django static storage (S3 in production), not a hardcoded
   backend `/static/` path. The vendored widget embeds its blob workers; retain
   the existing CSP without broader script or worker permissions.
3. Calibrate SMS daily limit from observed traffic and budget. Provider-side
   AWS End User Messaging limits remain the monetary backstop; message counts
   are not an exact dollar cap.
4. Remove the temporary `SEND_VERIFICATION_MODE=observe` override and select
   Enforce in the active admin configuration, or explicitly set the environment
   override to `enforce`. Confirm the admin's effective-policy display before
   cutover. Observation mode must have a defined end and must not remain as a
   client-selected bypass.

Rollback after enforcement: revert to a compatible protected frontend/backend
pair, or pause sending. Disabling server verification while leaving public
sends open is not the default rollback.

Stale clients that omit proofs receive `verification_required` and must reload
the current UI.

## Pending

- Production SMS daily limit and PoW cost calibration from live traffic.
- Authorized live smoke test of one email and one SMS path after enforce.
- Redis in production if multi-instance challenge throttling is required.

## Regression gate

Run `apps.authn.tests`, `apps.core.tests.commands.test_seed_service_configs`,
`apps.core.tests.commands.test_verify_service_configs`,
`apps.event.tests.views.test_sms_views`, and
`apps.event.tests.views.test_phone_verification` with mocked delivery. Dedicated
verification tests disable automatic proof attachment. The API coverage matrix
checks all 12 sending routes before account/contact mutations.

Run `apps.authn.tests.services.test_send_verification_concurrency` against an
isolated PostgreSQL 16 database with `config.settings.test` and the `DB_*`
variables. SQLite skips are not evidence of locking correctness. Contention and
fault tests must check provider calls, reservations, challenge consumption,
rollback, and retained OTPs, not just the database vendor name.

Browser regression tests must use the installed widget and actual worker with
valid low-cost challenges, without an injected proof or mocked solver. Cover
React, all three admin branches, real cookie path behavior, configured static
origins, solver errors, cancellation, duplicate clicks, and uncertain results.
Run frontend lint/types/build and migration consistency checks before review.

## Monitoring

Structured logs use the `apps.authn.send_verification` logger with hashed
destinations. Events include `challenge_issued`, `challenge_consumed`,
`proof_invalid`, `quota_*`, `send_rejected`, `send_finalized`, `request_replay`,
and `cleanup`. Do not log OTPs, HMAC secrets, or full proof payloads.

## Repair validation recorded on 2026-09-05

The repair addresses the 14 reviewed defects: actual recipient/channel binding,
React widget readiness, effective admin policy, production admin asset URLs,
operation-aware identity, remembered-cookie scope, uncertain delivery outcomes,
complete idempotency context, post-lock replay lookup, transaction conflict
rollback, malformed proof cost, widget error states, contact-email domain errors,
and event US-phone normalization. Additional regressions cover stable public
password-reset IDs, registration password fingerprints, and oversized challenge
destinations.

- PostgreSQL 16: **1043 backend tests passed**, with no skips, covering authn,
  related event SMS/phone views, and service-configuration commands. This includes
  actual contention tests using separate connections and barriers that force
  both initial request lookups to miss.
- After integration with current main, **1645 Vitest tests passed** across 143
  files. Coverage is 95.85% statements, 87.50% branches, 96.23% functions, and
  96.76% lines, meeting the unchanged repository thresholds.
- Chromium: **30 browser tests passed**, including seven real-widget/recovery
  tests and 23 existing login, phone, reset, and subscription journeys. The
  admin static-origin test serves the vendored UMD asset without CORS headers;
  the browser tests do not inject solved verification payloads.
- Django's five admin-adapter regressions passed, including CSRF rejection,
  remembered-cookie context, operation isolation, and static-storage URLs.
- Python Ruff, scoped frontend ESLint, TypeScript/production build, migration
  consistency, and whitespace checks passed.

Current-main integration also exercised 1087 PostgreSQL backend tests including
the provider-neutral email suites. Two legacy rejection fixtures needed the
provider error type used by SES/SMTP; after aligning them, all 20 tests in the
affected email API module passed on rerun. Six new transport regressions verify
SES/SMTP single dispatch, OTP retention after ambiguous outcomes, and confirmed
SMTP acceptance followed by a failed QUIT. The independent email and send-policy
migration branches are joined by a new merge migration.

All delivery providers were mocked. These results do not constitute production
deployment, live SMS/email delivery validation, or production budget calibration.

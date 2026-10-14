# Auth & Mail API

Authentication, member management, contact information, and email-related endpoints.

## Overview

The auth system is built on `rest_framework_simplejwt` with custom extensions for email-based verification, RSA password encryption, and multiple auto-login paths. All auth endpoints live under `/authn/` except the emailed login link (`/mail/login-link/`, legacy alias `/mail/magic-login/`).

## Code locations

| Concern | Path |
|---------|------|
| Views | `src/apps/authn/views/` (subpackages: `auth/`, `account/`, `admin/`) |
| Serializers | `src/apps/authn/serializers/` |
| Services | `src/apps/authn/services/` |
| Models | `src/apps/authn/models/` |
| URLs | `src/apps/authn/urls.py` |
| Throttles | `src/apps/authn/security/throttles.py` |
| Password-login lockout | `src/apps/authn/services/login_guard.py` |
| Mail views | `src/apps/mail/views/` |

## Rate-limit policy (no client-IP limits on sign-in)

Most legitimate users sit behind the same campus public IP, so a per-IP limit throttles everyone at once while a forged
`X-Forwarded-For` barely slows an attacker. **Sign-in, emailed-link, verification-code and ALTCHA-challenge endpoints
are therefore not limited per client IP.** What bounds them instead:

| Flow | Bound |
|------|-------|
| Login link, impersonation, newsletter unsubscribe and resubscribe | The token itself: about 384 bits and single use (login link, impersonation), or HMAC-signed with an expiry (unsubscribe 365 days, resubscribe 1 hour; both idempotent, see [One-click unsubscribe and resubscribe](#one-click-unsubscribe-and-resubscribe)) |
| Email code request, registration, resend, password reset by email | ALTCHA proof bound to operation, destination and browser session (`enforce` mode only; `observe` mode accepts a request without a proof); per-destination 60-second cooldown and hourly cap; per-member/purpose caps |
| Code verification (email and SMS) | Per-challenge attempt cap (email 5, SMS `MAX_VERIFY_ATTEMPTS` = 5), cut to 1 for codes issued to a destination with 10+ failed guesses in 24 hours ([code-guess degradation](../deployment/send-verification.md#code-guess-degradation)). The wrong guess that spends such a code is answered like any first wrong guess (`400`, the uniform invalid-code body) on every verify endpoint, email and SMS |
| SMS code request (phone auth, password reset by phone, and the authenticated SMS flows) | Per-number 60-second cooldown and 10 sends/hour; ALTCHA proof in `enforce` mode; the global SMS daily budget (`sms_daily_limit`), which counts SMS handed to the provider and nothing else ([SMS daily budget](../deployment/send-verification.md#sms-daily-budget)) |
| ALTCHA challenge issuance and status lookup | None per IP: a challenge sends nothing, and the send it authorises is capped per destination |
| Password login | Identifier-keyed failure lockout (below), plus site-wide spray *detection* (alarm only) |

Still limited per IP, and **only as a fallback while no SMS daily budget (`sms_daily_limit`) is configured**: the anonymous
SMS request endpoints (`POST /authn/phone-auth/request-code/` and `POST /authn/password-reset/request-code/` with a phone
identifier, 5/minute). Once the budget is set, SMS spend is bounded by it plus each number's cooldown and hourly cap, and
the per-IP throttle is no longer attached. Authenticated endpoints keep their per-user throttles. See [Send verification](../deployment/send-verification.md#client-ip-policy-and-residual-risks)
for the residual risks and [WAF rate limits](../deployment/waf-rate-limits.md) for the campus-aware edge rules.

**When the SMS daily budget is spent.** The budget is reserved only when an SMS is handed to the provider, so requests
that send nothing (a password reset for a number without an account, a number over its own hourly cap) do not use it.
Once it is spent, every flow that always sends an SMS (`POST /authn/phone-auth/request-code/`, password change by SMS,
contact-phone verification, the event phone code) answers:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 3600

{"code": "send_throttled", "detail": "The SMS sending budget for today has been reached.", "retry_after": 3600}
```

`POST /authn/password-reset/request-code/` never answers with the budget: it returns its usual neutral `202` and the SMS
is not sent, so the answer stays the same for a number with and without an account (see
[Password reset](#password-reset-post-authnpassword-resetrequest-codeverify-codeconfirm)). The window is the UTC day.

## Send verification (ALTCHA)

User-triggered verification-code sends require a self-hosted ALTCHA proof of
work. Proof of work does not prove the caller is human; destination quotas and
SMS budget controls are part of the same gate.

**`POST /authn/send-verification/challenge/`**

Request (never put the destination in a query string):

```json
{
  "operation": "email_auth.request_code",
  "email": "user@example.com"
}
```

Response (`200`, `Cache-Control: no-store`):

```json
{
  "challenge_id": "<uuid>",
  "expires_at": "<iso8601>",
  "algorithm": "PBKDF2/SHA-256",
  "cost": 5000,
  "challenge": {"parameters": {}, "signature": "..."}
}
```

**`GET /authn/send-verification/requests/<request_id>/`** returns the caller's
recorded send state after an ambiguous network result. Other users' ids are not
enumerable.

Public authentication requests bind to the browser session even if a Bearer
token is present. Account/event operations require the same authenticated
member for challenge, send, and status lookup. Admin uses the CSRF-protected
`POST /admin/send-verification/challenge/` route with its existing session and
remembered-account cookie; the public challenge route rejects admin operations.

Protected send bodies also accept:

```json
{
  "verification_challenge_id": "<uuid>",
  "verification_payload": "<base64>",
  "send_request_id": "<uuid>"
}
```

The same `send_request_id` may only be reused with the same principal, operation,
channel, normalized destination, and validated business inputs. A mismatch is
`409 send_request_conflict`. For password reset, send input uses `identifier`
then legacy `email`; an additional `destination` cannot override either.

An uncertain ordinary send returns `409` with `code: "send_unknown"`,
`request_id`, and an optional OTP `challenge_id`. Query the original request on
this response or a network error; do not automatically resend. Status responses
contain `request_id`, `status`, `http_status`, `code`, `result`, and
`challenge_id`. States are `pending`, `sending`, `provider_accepted`,
`definitely_failed`, and `unknown`. Acceptance does not mean delivery.

Password reset preserves account-enumeration protection: business outcomes
share a neutral `202` response and opaque challenge identifier. Its public
status is `submitted`, not a delivery-success claim; actual delivery outcomes
remain internal. Proof/authentication failures and site-wide sending limits
still reject the request before the protected business action.

See [Send verification](../deployment/send-verification.md) for operations,
error codes, quotas, and cutover.

## Registration

### `POST /authn/register/`

Creates a new member account. Passwords are RSA-encrypted by the frontend before transmission.

**Request:**
```json
{
  "email": "user@example.com",
  "first_name": "Jane",
  "last_name": "Doe",
  "organization": "Example Inc.",
  "title": "Engineer",
  "password": "<base64 ciphertext>",
  "password_confirm": "<base64 ciphertext>",
  "key_id": "<uuid>"
}
```

**Response (`202 Accepted`):**

```json
{
  "message": "Registration started. Check your email for a verification code.",
  "next_step": "verify_code"
}
```

Registration creates or updates an inactive member, sends a registration challenge, and activates the account only when `/authn/register/verify-code/` consumes the code. The verification response returns JWT tokens and user data.

**Validation:**
- HTML tags rejected in `first_name` and `last_name` (XSS prevention)
- `organization` is required; `title` is optional
- Email must not conflict with an existing active/claimed account; the matching inactive pending registration may be resumed
- Both password fields are decrypted server-side using the matching RSA key ID, validated, and required to match

**Serializer:** `src/apps/authn/serializers/register.py` (`RegisterSerializer`)

## Login

### `POST /authn/login/`

Password-based login with an **email or phone** identifier and an RSA-encrypted password.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "<base64 ciphertext>",
  "key_id": "<uuid>"
}
```

The `email` field accepts an email address or a phone number and is kept for backward
compatibility; an explicit `identifier` field is also accepted and takes precedence when
both are sent. The identifier is resolved via `resolve_login_identifier`
(`services/email/auth_email.py`): an `@`-containing value matches a **verified** `ContactEmail`
(email-first), otherwise the digits are normalized and matched against a **verified**
`ContactPhone`. Unverified contacts never authenticate.

**Response:**
```json
{
  "access": "<jwt>",
  "refresh": "<jwt>",
  "user": {
    "member_uuid": "<uuid>",
    "email": "user@example.com",
    "phone": "+12095551234",
    "is_staff": false
  },
  "next_step": "account",
  "requires_profile_completion": false
}
```

**Behavior:**
- Generic error message ("Invalid credentials.") for every failure mode (wrong password,
  unknown identifier, unverified phone, inactive account) to prevent account enumeration
- Phone-only accounts can sign in here once they have set a password (see *Password management*),
  and continue to use the passwordless phone-OTP flow (`/authn/phone-auth/*`)
- The supplied `key_id` selects the exact active or retained RSA key; the backend never tries another key
- Not throttled per IP; guessing is bounded per identifier by the failure lockout below

**Failure lockout (`429`, `code: "login_locked"`).** After **10 credential failures in 15 minutes** or **30 in 24 hours**
for the same identifier, further attempts are refused until the window that tripped ends:

```json
{
  "detail": "Too many failed sign-in attempts. Please try again later or sign in with an email code.",
  "code": "login_locked"
}
```

The response carries `Retry-After` (seconds until the lock lifts). Rules:

- The lock is checked **before** the password is decrypted or hashed, so a locked identifier costs the server almost nothing,
  and a correct password does not bypass it.
- Only credential failures count: wrong password and unknown, inactive or unverified identifiers, all treated identically, so
  neither the count nor the lock reveals whether an account exists (the 429 body is byte-identical for every identifier).
  Malformed requests (missing fields, non-string values, an undecryptable password) are never counted.
- The key is a `SECRET_KEY`-salted HMAC of the normalised identifier (email trimmed and case-folded; phone reduced to national
  digits, so every format of one number is one identifier); no email or phone is stored. The client IP plays no role:
  different identifiers, and different IPs, are independent; one IP failing for many identifiers is never locked as a whole.
- A successful sign-in clears that identifier's counters. Windows are fixed and aligned to the clock (15 minutes and UTC days).
- Only password sign-in is affected: email codes, login links and the phone flow still work, which is what the message steers
  users to.

Limits and caveats: a member with several verified emails plus a phone has one budget per identifier (the lock cannot be keyed
on the member without becoming an enumeration oracle). Anyone who knows an address can lock that account's *password* sign-in
for up to the rest of the window by failing on purpose; email-code sign-in is the way through.

**Storage.** Counters live in PostgreSQL, table `authn_loginfailurewindow` (model `LoginFailureWindow`): one row per
identifier digest and clock-aligned window, unique on `(identifier_digest, window, window_index)`. A failure is one atomic
`UPDATE ... SET failure_count = failure_count + 1` (inserting the row for the window's first failure; a lost insert race
counts on the winner's row), so every Uvicorn worker and every ECS task shares the same counts, concurrent failures are never
lost, nothing evicts them and `Retry-After` is exact. No Redis is needed. A burst can overshoot a limit by at most one attempt
per request already past the check. Database errors fail the request (no fail-open). Ended windows are deleted by the
background worker's hourly maintenance (`purge_expired_failure_windows`, 1000 rows per statement), which never lifts a live
lock. A successful sign-in deletes only the identifier's rows for the windows in progress (the rows the lock check reads) and
leaves ended ones to that purge, so a sign-in and the purge do not delete the same rows.

**Spray detection.** Every counted failure also increments one site-wide row per 5-minute window. The failure that brings it to
`SPRAY_ALERT_THRESHOLD` (200) logs one WARNING, `login_guard.failure_spike failures=200 window=5m threshold=200`, for a
CloudWatch Logs metric filter and alarm ([Monitoring](../deployment/send-verification.md#monitoring)). Nothing is refused: a
global block would lock the whole campus out at once. A successful sign-in clears only that identifier's rows, not the
site-wide count.

The admin-panel password login (`/admin/login/`) uses the same guard; the client IP plays no role there either. Its two
forms count separately:

- **Email + password form.** An unknown address, a wrong password and a non-staff account all count against the submitted
  email: the same counter as `POST /authn/login/` for that address, so an attacker does not get one allowance per entry
  point. Like the member login, this form can therefore be locked from anywhere by anyone who knows a staff address. That is
  by design: the address is the only thing an anonymous request can be counted by.
- **Remembered-admin form.** It posts no email; the account is the one in the signed, HttpOnly `i2g_last_admin_member`
  cookie, which a browser only holds after signing in to the admin as that member. It counts on a
  `login_guard.ScopedKey` (scope `admin-remembered`, subject the member id), never on the member's email. Scoped keys are
  hashed under a different HMAC key than typed identifiers, so nothing typed into any endpoint reaches that counter, the
  literal text `admin-remembered:<member id>` included. Failing for a staff address on the member login or on the email +
  password form therefore never locks a returning admin's remembered form. Only a holder of the cookie can lock it, and
  that leaves the email + password form open.

Each form has the usual limits (10 failures per 15 minutes, 30 per UTC day), refuses a locked counter before any password
work with "Too many login attempts. Please try again later.", and clears only its own counter on a successful sign-in.
Failures on either form count towards spray detection. The email-code admin login is not password based, so this lockout
never applies to it; its code requests are bounded separately by the per-destination send limits
([Send verification](#send-verification-altcha)).

### `GET /authn/public-key/`

Returns the current RSA public key for password encryption. Frontend caches this for 5 minutes.

**Response:**
```json
{
  "key_id": "<uuid>",
  "public_key": "<PEM-encoded RSA public key>"
}
```

The active key is named `auth-encryption`. Public-key retrieval rotates a key
older than one day into a new row with a new `key_id`. Retired rows remain
eligible for decryption for 24 hours and are retained, then purged
opportunistically, at 48 hours. Unknown and expired IDs fail closed.

Clients should cache the response only briefly, retain `key_id` with the ciphertext, and clear/refetch the key after a decryption/key-ID error. They must re-encrypt with the replacement public key; ciphertext cannot safely be retried under another key.

## Passwordless phone authentication

### `POST /authn/phone-auth/request-code/`

Starts passwordless signup or login with a US phone number.

**Request:**

```json
{
  "phone_number": "2095551234",
  "region": "1-US",
  "source": "login"
}
```

`source` may be `login`, `subscribe`, or `event_registration`; it is currently validated for parity with email auth but does not change phone-auth behavior.

The SMS service caps each destination at 10 sends/hour, send verification adds a 60-second per-destination cooldown, and the global SMS daily budget (`sms_daily_limit`), when configured, caps all SMS sends together. Because every number that asks does get an SMS here, a spent budget is answered truthfully: `429` with `code: "send_throttled"`, `detail: "The SMS sending budget for today has been reached."`, `retry_after: 3600` and a `Retry-After: 3600` header. The public request takes a 5/minute per-IP throttle **only as a fallback while no SMS daily budget is configured** (`sms_request_throttles()`); setting the budget in Site Settings removes it without a deploy. Verification (`verify-code`) has no per-IP throttle, only the per-challenge attempt cap (5, or 1 for codes sent to a number with 10+ failed guesses in 24 hours).

**Response (`202 Accepted`):**

```json
{
  "message": "If this number can receive SMS, a verification code has been sent.",
  "challenge_id": "<uuid>"
}
```

### `POST /authn/phone-auth/verify-code/`

**Preferred request:**

```json
{
  "challenge_id": "<uuid>",
  "region": "1-US",
  "code": "123456"
}
```

On success, the endpoint atomically consumes the challenge, resolves or creates the phone member, and returns the standard JWT auth payload. Deactivated accounts receive the same generic invalid-code response as other failures.

A wrong code answers `400` with `{"detail": "Verification code is invalid or has expired."}`. The wrong guess that uses up a normal code's fifth attempt answers `429` (`"Too many verification attempts. Please try again later."`) and the code is spent. A code sent to a number under guessing attack allows one guess: a wrong guess spends it and still answers the plain `400` above, exactly like a first wrong guess on any other number, so the answer does not show that the number is degraded. Either way a new code must be requested.

For one compatibility release, callers may omit `challenge_id` and send `phone_number` instead. That path resolves the latest pending `phone_auth` challenge for the normalized number. New clients must persist the request response's `challenge_id` and send it back; the compatibility lookup will be removed.

## Email auth challenges

A unified two-step verification flow used for multiple purposes.

### `POST /authn/email-auth/request-code/`

Creates an `EmailAuthChallenge` and sends a 6-digit code via email.

**Request:**
```json
{
  "email": "user@example.com",
  "source": "login"
}
```

**Sources:** `login`, `subscribe`, `event_registration`

**Behavior:**
- If the email belongs to an active verified account, the challenge purpose is `login`
- Otherwise the flow creates or reuses an inactive pending member and issues a `register` challenge
- Public email-auth emails now include both a 6-digit code and a frontend GET link:
  - `/email-auth-link?flow=auth&source=...&email=...&code=...`
- Code hashed before storage (never stored in plain text)
- Expires after 10 minutes
- Maximum 5 verification attempts (1 when the address has 10+ failed guesses across its codes in the last 24 hours)
- Not throttled per IP; bounded by the ALTCHA proof and the per-destination cooldown and hourly cap

### `POST /authn/login/request-code/`

Sends a 6-digit login code for an existing verified account email.

**Behavior:**
- Email includes both the 6-digit code and a frontend GET login link:
  - `/email-auth-link?flow=login&source=login&email=...&code=...`

### `POST /authn/email-auth/verify-code/`

Validates a unified login/registration code, consumes it, and returns the standard JWT auth payload.

**Request:**
```json
{
  "email": "user@example.com",
  "code": "123456"
}
```

**Response:**
```json
{
  "message": "Login successful.",
  "access": "<jwt>",
  "refresh": "<jwt>",
  "user": {
    "member_uuid": "<uuid>",
    "email": "user@example.com",
    "phone": null,
    "is_staff": false
  },
  "next_step": "account",
  "requires_profile_completion": false
}
```

**Not throttled per IP:** guesses are bounded per challenge (5 attempts, 1 for codes issued while the address is degraded),
never per client address.

Login and registration verify endpoints consume their challenge while issuing JWTs. Password, account-deletion, and contact-verification flows either consume the code for the protected action or mint a separate one-time `verification_token`. Challenge rows are locked while attempts are checked; failed-attempt and expiry updates commit before the API returns an error. Conditional status transitions prevent two concurrent requests from consuming the same code or verification token.

## Frontend email link landing

### `GET /email-auth-link`

Frontend-only landing page used by auth emails. Before third-party scripts run,
the bootstrap captures `flow`, `source`, `email`, and `code` from the URL
fragment into route-specific `sessionStorage` and immediately scrubs the URL.
React consumes and deletes that stored callback. Legacy query-string links stay
accepted through the documented compatibility window, but newly generated links
use fragments.

- `flow=auth` -> `POST /authn/email-auth/verify-code/`
- `flow=login` -> `POST /authn/login/verify-code/`
- `flow=register` -> `POST /authn/register/verify-code/`

On success it stores JWT credentials in the SPA and routes based on `source`.

## Password management

Both the authenticated **create/change-password** flow and the unauthenticated
**password-reset** flow verify the user through a recovery contact before a password is set.
Verification can happen over **email** (a hashed `EmailAuthChallenge` code) or, when no
verified email exists, **SMS** (a durable `PhoneVerificationChallenge`). On a successful code
check, a one-time `verification_token` is minted (stored hashed on a `VERIFIED`
`EmailAuthChallenge` row) and consumed by the matching `confirm` step. The SMS channel reuses
the same token/confirm path — it is not a parallel confirmation mechanism — via a channel-aware
`EmailAuthChallenge` (`channel`, `target_phone` fields) after consuming the SMS challenge.

### Verification-channel selection

For the authenticated create/change-password flow the channel is chosen by
`select_recovery_channel` (`services/account_recovery/channel_select.py`) in this order:

1. a verified **primary** email;
2. otherwise **any** verified contact email;
3. otherwise a verified **phone** via SMS;
4. otherwise a `400` validation error (*"No verified email or phone is available…"*).

For the password-reset flow the channel follows the identifier the caller supplied (email → email,
phone → SMS).

### `POST /authn/change-password/request-code/`

Authenticated. `email` is **optional** — when omitted, the channel is selected automatically (the
phone-only path). When supplied it must be one of the member's verified emails (used to
disambiguate between several verified emails).

- **Response:** `{ "message": "...", "channel": "email" | "sms", "destination": "<masked>", "challenge_id": "<SMS only>" }`
- Every successful SMS issuance includes `challenge_id`; persist it until verification. Delivery failure returns a non-2xx response and is never reported as “sent.”
- Throttled per-user for both email and SMS sends; the SMS service also enforces a per-number cap.

### `POST /authn/change-password/verify-code/`

Authenticated. Body: `{ "code": "<6 digits>", "email": "<optional>", "channel": "<optional>", "challenge_id": "<SMS only>" }`.
Verifies the code on the selected channel and returns `{ "message": "...", "verification_token": "...", "channel": "..." }`.
For SMS, `challenge_id` is preferred; omitting it uses the temporary phone-number compatibility lookup.

### `POST /authn/change-password/confirm/`

Authenticated. Body: `{ "verification_token", "new_password", "new_password_confirm", "key_id" }`.
Consumes the token (channel-agnostic) and sets the password. Unchanged by the SMS work.

> `POST /authn/change-password/` (the separate *current-password* change endpoint) is unchanged.

### Password reset (`POST /authn/password-reset/{request-code,verify-code,confirm}/`)

Unauthenticated, enumeration-safe. Accepts an `identifier` (email **or** phone; `email` kept as a
backward-compatible alias). The request step always returns the same generic message regardless of
whether an account exists. Verify returns a uniform `"Verification code is invalid or has expired."`
error and confirm returns `"Verification token is invalid or has expired."`, so neither step reveals
account existence. The public request endpoint
can apply the per-IP SMS throttle (5/minute) only when the identifier is a phone number, and then only as a fallback while no
SMS daily budget is configured; an email identifier never has a per-IP throttle and is bounded by the per-destination cooldown
and hourly cap.

The SMS daily budget never changes the request answer. A reset sends an SMS only when the number belongs to an active
account, and only that SMS reserves a budget unit; a number without an account costs nothing. When the budget is spent,
the request still returns the neutral `202` and no SMS is sent, for a number with and without an account alike (status,
body and headers are identical). A `429` here would be an answer only real accounts could get. The refusals a reset can
return are decided before the account is looked at and are the same for every number: the proof check, the
per-destination cooldown (`429 send_throttled`, "Please wait before requesting another code.") and `503` while `enforce`
mode has no SMS daily limit configured.

The request response always includes an opaque `challenge_id`: the stable protected-send request
UUID for every outcome. It does not change while dispatch is in progress. Phone verification resolves
it internally to the matching reset OTP, checking operation and destination before code validation.
Legacy direct SMS challenge IDs remain accepted. Echo `challenge_id` to `verify-code` when the
identifier is a phone:

```json
{
  "identifier": "+12095551234",
  "code": "123456",
  "challenge_id": "<uuid from request-code>"
}
```

During the compatibility release, phone reset verification may omit the ID and resolve the latest
pending challenge for that phone and `password_reset` purpose. New clients must not rely on that lookup.

## Token refresh

### `POST /authn/refresh/`

Standard SimpleJWT token refresh with rotation.

**Request:** `{ "refresh": "<token>" }`

**Response:** `{ "access": "<new_token>", "refresh": "<new_token>" }`

The old refresh token is blacklisted after rotation.

## Session bootstrap

### `GET /authn/session/`

Authenticated. Returns the current server-side member/profile state used to rehydrate a persisted frontend token session.

**Response:**

```json
{
  "user": {
    "member_uuid": "<uuid>",
    "email": "user@example.com",
    "email_verified": true,
    "primary_email_id": "<uuid>",
    "first_name": "Jane",
    "middle_name": "",
    "last_name": "Doe",
    "organization": "Example Inc.",
    "title": "Engineer",
    "email_subscribe": true,
    "is_active": true,
    "date_joined": "2026-07-25T00:00:00+00:00",
    "profile_image": null,
    "phone": "+12095551234",
    "is_staff": false
  },
  "requires_profile_completion": false,
  "next_step": "account"
}
```

`next_step` is `complete_profile` when the member lacks required profile fields and `account` otherwise. The endpoint returns `401` for a missing, invalid, or expired access token; it does not refresh tokens itself. The first-party auth client handles one refresh-and-retry through `/authn/refresh/`, then writes this response only if the same local session generation is still current.

## Profile

### `GET /authn/profile/`

Returns the authenticated user's profile data.

### `PATCH /authn/profile/`

Updates profile fields. JSON supports `first_name`, `last_name`, `middle_name`, `organization`, `title`, and `email_subscribe`. Multipart requests may upload `profile_image` (JPEG, PNG, GIF, or WebP, maximum 5 MB).

`email_subscribe` is not a member field: it reads and writes the `subscribe` flag of the primary contact email only (see [Contact emails](#contact-emails)).

## Contact emails

Every contact email has its own `subscribe` flag, and that flag alone decides whether the address receives newsletters
(the *All Email Subscribers* campaign audience; see
[Member & Mail Tools](../cms-admin/member-and-mail-tools.md#audience-types)). There is no member-level subscription
setting: the account page and the Subscribe page edit these per-address flags, and the
[one-click unsubscribe link](#one-click-unsubscribe-and-resubscribe) turns off all of them at once.

### `GET /authn/contact-emails/`

Lists the authenticated user's contact emails.

### `POST /authn/contact-emails/`

Creates a new contact email. Throttled: 5/hour. Verification status is independent of primary status
(a new email is always created unverified).

**Primary-email invariant:** a member who owns any contact email must have exactly one `primary`.
When the member has **no** primary (their first email, or a legacy gap), the new email is forced to
`primary` regardless of the requested `email_type`; this is decided atomically under a row lock so
concurrent adds can't create two primaries. Adding a further email while a primary exists keeps the
requested type and never replaces the existing primary. (Existing inconsistent rows are repaired by
data migration `0016`: promote one email when none is primary — prefer verified, else oldest — and
demote extras when several are primary.)

### `PATCH /authn/contact-emails/{id}/`

Updates a non-primary contact email's type (`secondary` or `other`) and/or subscribe status. Directly demoting or assigning `primary` is rejected; promote a different verified email through `make-primary` so the swap remains atomic.

### `DELETE /authn/contact-emails/{id}/`

Deletes a contact email, enforcing the recovery-contact policy atomically:

- Deletion is **blocked** (`409 Conflict`, actionable message) when removing the email would leave the
  member with **no verified recovery contact**. A verified phone or another verified email counts as a
  survivor; deleting an *unverified* email is always allowed. A phone-only account with a verified
  phone may therefore hold zero emails.
- If the deleted email was `primary`, another remaining email is promoted deterministically (prefer
  verified, else oldest). If no email remains, the account may have no primary.
- Email and phone deletions both lock the owning member row before counting survivors. That shared
  cross-table mutex prevents simultaneous deletes from each removing what appeared to be the other
  verified recovery method.

### `POST /authn/contact-emails/{id}/request-verification/`

Sends an email verification challenge.

### `POST /authn/contact-emails/{id}/verify-code/`

Consumes the six-digit code and marks the email verified.

### `POST /authn/contact-emails/{id}/make-primary/`

Promotes a verified contact email to primary (atomic; the previous primary is demoted).

## Contact phones

### `GET /authn/contact-phones/`

Lists the authenticated user's contact phones.

### `POST /authn/contact-phones/`

Creates a new contact phone. SMS verification is requested separately via `request-verification/`.

### `POST /authn/contact-phones/{id}/request-verification/`

Sends an SMS OTP and returns `202 Accepted` with `{ "message": "...", "challenge_id": "<uuid>" }`.
Requests are throttled to 5/minute per authenticated member, in addition to the service's per-destination cap.

### `POST /authn/contact-phones/{id}/verify-code/`

Preferred body: `{ "code": "123456", "challenge_id": "<uuid>" }`. The contact record identifies the phone number and the challenge ID identifies the exact `contact_phone_verify` issuance. A code-only body remains accepted for one compatibility release.

### `DELETE /authn/contact-phones/{id}/`

Deletes a contact phone. Enforces the **same** last-verified-recovery-contact rule as email deletion
(symmetric): removing a *verified* phone is blocked with **409** when it would leave the member with no
verified recovery contact (a verified email or another verified phone counts as a survivor). Deleting an
unverified phone is always allowed.

> Note: the unauthenticated **Subscribe** and **Event Registration** entry screens accept an email **or**
> a phone identifier (the existing passwordless code flows, `source=subscribe` / `event_registration`);
> the event ticket is still delivered to an email collected on the registration form. The Subscribe page has no
> endpoint of its own: after signing in it sets the flags through `PATCH /authn/profile/` (`email_subscribe`, the
> primary address) and `PATCH /authn/contact-emails/{id}/` / `PATCH /authn/contact-phones/{id}/` (`subscribe`).

## Account deletion

### `POST /authn/delete-account/{request-code,verify-code,confirm}/`

Authenticated three-step email challenge. `verify-code` mints a one-time `verification_token`; `confirm` consumes it before permanently deleting the member account. An account without a verified primary email must add and verify one before deletion.

## Auto-login endpoints

Token-based paths for email-originated actions:

| Endpoint | Token source | Service |
|----------|-------------|---------|
| `POST /authn/impersonate-login/` | Five-minute admin-issued impersonation token | `src/apps/authn/views/admin/impersonate_login.py` |
| `POST /mail/login-link/` | Login link in campaign and ticket emails (`LoginLinkToken`) | `src/apps/mail/views/login_link.py` |
| `POST /mail/magic-login/` | Legacy alias of `/mail/login-link/` for already-sent emails | `src/apps/mail/views/login_link.py` |

`/mail/login-link/` validates the token (validity frozen at send time; one-time by default, reusable per campaign/event opt-in) and returns JWT access/refresh tokens plus `redirect_to`.

`/authn/impersonate-login/` accepts `{ "token": "..." }`. It conditionally marks an unused, unexpired token as used before issuing JWTs. Exactly one request can win a concurrent exchange; later requests receive an already-used or expired `400` response.

**Removed endpoints.** `POST /authn/unsubscribe-login/` (the exchange behind the old `/unsubscribe-login#token=X` email links) and `POST /authn/subscribe/` (an anonymous newsletter sign-up with a 30/minute per-IP throttle, which the SPA no longer called) no longer exist and return `404`. Newsletter opt-out is the backend page behind the [one-click unsubscribe link](#one-click-unsubscribe-and-resubscribe), plus the per-address flags on `/account`; the SPA keeps `/unsubscribe-login` only as a redirect to `/account` that drops the old token and calls nothing.

The emailed links carry their token in the URL fragment (`/login-link#token=X`, `/impersonate-login#token=X`); the frontend still accepts the legacy `?token=X` query form. A missing, blank, or non-string `token` (or a non-object body) returns `400 "Token is required."`; so does a token that could never be real and is therefore never looked up: one the database layer cannot take (a lone UTF-16 surrogate, or a NUL character) or one longer than 2048 characters once trimmed (real tokens are at most 128; `MAX_CREDENTIAL_LENGTH` in `src/apps/authn/views/helpers.py`).

The application-level `400` rejections of `/mail/login-link/` (`token_required`, `invalid_link`, `expired`, `already_used`) carry a stable machine-readable `code` next to the unchanged `detail`; `invalid_link` covers both an unknown token and an inactive member, which are deliberately indistinguishable. Framework-generated errors (`415` unsupported media type, unparseable JSON) carry only `detail`, so clients branch on the HTTP status for those and use `code` only for the four rejections above. None of the token endpoints (login link, impersonation, one-click unsubscribe and resubscribe) is throttled per client IP (campus users share one address; the token is the control), so they never answer `429`.

The `expired` and `already_used` rejections also carry `redirect_to`: the link's own post-login destination, the same value a successful exchange returns (the campaign's post-login destination, or the ticket link's `/event-registration?event=<slug>`; the server keeps a stored path only when it starts with a single `/`, and returns `/account` when the link has none or an unsafe one). A client that cannot use the link and falls back to another sign-in method can send the member where the email intended. It is not account state, and only a caller holding the real token gets it: `token_required` and `invalid_link` (unknown token or inactive member) never include it, so an inactive member's response stays byte-identical to an unknown token's. `redirect_to` is optional for clients; when it is absent (an older backend), use the default landing.

**Clients MUST re-validate `redirect_to` before navigating to it, on the `400` bodies and on the `200` body alike.** The server-side check is deliberately weaker than the SPA's: it only requires a leading `/` and no leading `//`, so it does not reject backslashes (`/\evil.example`), control or whitespace characters, or percent-encoded slashes (`/%2f/evil.example`), which some browsers or downstream parsers fold into an off-site target. The SPA passes every `redirect_to` through `getSafeInternalRedirectPath` (`pages/src/features/auth/api/redirects.ts`) and falls back to `/account` when it returns `null`; other clients must apply an equivalent check.

**Credential-exchange views set `authentication_classes = []`** (login-link, impersonation, logout, one-click unsubscribe, resubscribe; refresh inherits it from SimpleJWT). Each is authenticated by a credential the request itself carries (an emailed token or a refresh token), but the SPA attaches its stored access token to every request and DRF authenticates before checking permissions, so a stale, expired, or other-account `Authorization: Bearer` header would return `401` before the credential was consumed. A refresh token whose member was deleted returns `401`, never `500`.

## Admin invitation

### `GET|POST /authn/invite/{token}/`

Server-rendered invitation form. A valid pending token either upgrades an existing verified member or collects profile/password fields and creates the staff account. Invalid or expired tokens return the invitation error page.

## Mail system

The mail app (`src/apps/mail/`) handles email campaigns and exposes login-link exchange, one-click unsubscribe/resubscribe, and the SES event webhook. Campaign management is done through Django admin — see [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md).

### One-click unsubscribe and resubscribe

Standalone backend HTML pages (`src/apps/mail/views/subscriptions.py`, logic in `src/apps/mail/services/subscriptions.py`), authenticated only by the signed token in the URL. They read no JWT, CSRF token or request body, have no throttle (the token is the control), are never cached (`never_cache`), are `noindex`, and never list the member's addresses. They always answer with their HTML page, so an unusual `Accept` header or a `?format=` parameter cannot turn a request into a `406` or `404`. When `FRONTEND_URL` is set, each page links to `FRONTEND_URL/account` ("Manage email preferences"), where every address has its own flag.

#### `GET|HEAD|POST /mail/unsubscribe/{token}/`

The link behind a campaign's footer "Unsubscribe from newsletters" and its RFC 8058 `List-Unsubscribe` / `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers. A campaign adds both when **Include one-click unsubscribe** is on (the default), for every recipient that is a member, whatever the audience; manual addresses get neither, and nothing is added while `BACKEND_URL` is unset. The token is the member id signed with `SECRET_KEY` (salt `rfc8058-one-click-unsubscribe`, unchanged, so links already in inboxes keep working). It is valid for **365 days** and reusable until then. Rotating `SECRET_KEY` breaks every link already sent: the settings define no `SECRET_KEY_FALLBACKS`.

- **`GET` and `HEAD` change nothing.** Link scanners and mailbox prefetchers fetch every link in a message. If any address of the member is still subscribed, `GET` shows a confirmation page whose form posts back to the same URL; otherwise it shows the "you've been unsubscribed" page, without a resubscribe button.
- **`POST` unsubscribes the person:** it turns off `subscribe` on **every** contact email of the member, not only the address the message went to. The RFC 8058 one-click request from the mailbox provider (any content type, body ignored) and the confirmation form both land here. It is idempotent: a replay, a second click or an already-unsubscribed member gets the same `200` page and changes nothing. Inactive members can unsubscribe too. An address added later has its own flag: one added on `/account` gets the flag chosen there, and one an event registration adds is subscribed only while another address of the member is, so a registration never undoes the opt-out.
- The rows are switched under the member-row lock that every contact-email change takes, so concurrent requests cannot both count as the change. The confirmation email ("You've been unsubscribed") is sent after the commit and only when at least one address changed, to the primary address (else the oldest changed one). A replay changes nothing and so sends nothing. At most one confirmation goes out per member and action (unsubscribe, resubscribe) per hour, whatever toggles the flags: the links are reusable, so whoever holds a forwarded newsletter link could otherwise unsubscribe and resubscribe in a loop and mail the member on every round. With the outbox the bound is its dedupe key (member, action, clock hour), shared by every container; without it, a per-process marker in the `throttle` cache. The flag changes themselves are not limited.
- The done page offers **Re-subscribe** with a fresh resubscribe token for exactly the addresses this `POST` turned off. A `POST` that changed nothing (a replay, a second click, or a member who had already opted out, e.g. on `/account`) gets no button, only the account link: a forwarded or old link must not be a way to turn a deliberate opt-out back on. Inactive members get no button.
- An invalid, expired or tampered token, or one whose member no longer exists, returns `400` with the account link.

#### `POST /mail/resubscribe/{token}/`

`POST` only (`GET`, `HEAD` and `OPTIONS` return `405`); the done page's form posts here through a relative URL, so it stays same-origin under CSP `form-action 'self'` on the backend host and behind the `/api` proxy alike. The token (salt `mail-resubscribe`) is valid for **1 hour** and reusable within it. It carries the ids of the addresses the unsubscribe turned off; ids that no longer belong to the member are ignored, and a token issued before per-address resubscribe (no ids) restores the primary address only. It turns `subscribe` back on for those addresses, idempotently, under the same lock, and sends "You've been resubscribed" only when something changed. When nothing changed (a second click, or addresses already subscribed or gone), the page says "No changes made" instead of claiming a resubscribe. An invalid or expired token, or one for an inactive or deleted member, returns `400`.

## Related pages

- [Architecture: Request Flow](../architecture/request-flow.md) — Login and token refresh sequences
- [Architecture: Frontend](../architecture/frontend.md) — Auth provider and crypto implementation
- [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md) — Email campaign admin
- [Routing Overview](routing-overview.md) — Full URL map

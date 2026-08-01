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
| Throttles | `src/apps/authn/throttles.py` |
| Mail views | `src/apps/mail/views/` |

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
- Throttled: 10 requests/minute (`LoginRateThrottle`)

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

The public request is throttled to 5/minute per IP, and the SMS service caps each destination at 10 sends/hour.

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
- Maximum 5 verification attempts
- Throttled: 30 requests/minute

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

**Throttled:** 60 requests/minute

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
applies a per-IP SMS throttle when the identifier is a phone number.

The request response always includes an opaque `challenge_id` so its shape is enumeration-safe. It
is the real durable SMS challenge ID only for an eligible phone account; email and unknown identifiers
receive an unrelated decoy UUID. Echo `challenge_id` to `verify-code` when the identifier is a phone:

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

## Contact emails

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
> the event ticket is still delivered to an email collected on the registration form.

## Account deletion

### `POST /authn/delete-account/{request-code,verify-code,confirm}/`

Authenticated three-step email challenge. `verify-code` mints a one-time `verification_token`; `confirm` consumes it before permanently deleting the member account. An account without a verified primary email must add and verify one before deletion.

## Auto-login endpoints

Token-based paths for email-originated actions:

| Endpoint | Token source | Service |
|----------|-------------|---------|
| `POST /authn/unsubscribe-login/` | Unsubscribe link in emails (no JWT; preference-only) | `src/apps/authn/views/` |
| `POST /authn/impersonate-login/` | Five-minute admin-issued impersonation token | `src/apps/authn/views/impersonate_login.py` |
| `POST /mail/login-link/` | Login link in campaign and ticket emails (`LoginLinkToken`) | `src/apps/mail/views/login_link.py` |
| `POST /mail/magic-login/` | Legacy alias of `/mail/login-link/` for already-sent emails | `src/apps/mail/views/login_link.py` |

`/mail/login-link/` validates the token (validity frozen at send time; one-time by default, reusable per campaign/event opt-in) and returns JWT access/refresh tokens plus `redirect_to`.

`/authn/impersonate-login/` accepts `{ "token": "..." }`. It conditionally marks an unused, unexpired token as used before issuing JWTs. Exactly one request can win a concurrent exchange; later requests receive an already-used or expired `400` response.

## Admin invitation

### `GET|POST /authn/invite/{token}/`

Server-rendered invitation form. A valid pending token either upgrades an existing verified member or collects profile/password fields and creates the staff account. Invalid or expired tokens return the invitation error page.

## Mail system

The mail app (`src/apps/mail/`) handles email campaigns and exposes login-link exchange, one-click unsubscribe/resubscribe, and the SES event webhook. Campaign management is done through Django admin — see [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md).

## Related pages

- [Architecture: Request Flow](../architecture/request-flow.md) — Login and token refresh sequences
- [Architecture: Frontend](../architecture/frontend.md) — Auth provider and crypto implementation
- [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md) — Email campaign admin
- [Routing Overview](routing-overview.md) — Full URL map

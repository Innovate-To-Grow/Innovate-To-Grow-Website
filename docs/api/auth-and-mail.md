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
| Mail views | `src/apps/mail/views.py` |

## Registration

### `POST /authn/register/`

Creates a new member account. Passwords are RSA-encrypted by the frontend before transmission.

**Request:**
```json
{
  "email": "user@example.com",
  "first_name": "Jane",
  "last_name": "Doe",
  "encrypted_password": "<base64>",
  "key_id": "<uuid>"
}
```

**Response:** Returns JWT tokens and user data. Registration creates active users immediately — no email verification step.

**Validation:**
- HTML tags rejected in `first_name` and `last_name` (XSS prevention)
- Email must not be already registered
- Password decrypted server-side using matching RSA keypair

**Service:** `src/apps/authn/services/create_member.py` (`CreateMemberService`)

## Login

### `POST /authn/login/`

Password-based login with an **email or phone** identifier and an RSA-encrypted password.

**Request:**
```json
{
  "email": "user@example.com",   // email address OR phone number (e.g. "2095551234", "+1 209 555 1234")
  "password": "<base64>",        // RSA-encrypted
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
  "user": { "member_uuid": "<uuid>", "email": "...", "phone": "...", ... },
  "requires_profile_completion": false
}
```

**Behavior:**
- Generic error message ("Invalid credentials.") for every failure mode (wrong password,
  unknown identifier, unverified phone, inactive account) to prevent account enumeration
- Phone-only accounts can sign in here once they have set a password (see *Password management*),
  and continue to use the passwordless phone-OTP flow (`/authn/phone-auth/*`)
- RSA keypair rotated on each successful login
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
- Throttled: 10 requests/minute

### `POST /authn/login/request-code/`

Sends a 6-digit login code for an existing verified account email.

**Behavior:**
- Email includes both the 6-digit code and a frontend GET login link:
  - `/email-auth-link?flow=login&source=login&email=...&code=...`

### `POST /authn/email-auth/verify-code/`

Validates the code and returns a verification token for the final action.

**Request:**
```json
{
  "email": "user@example.com",
  "code": "123456",
  "purpose": "password_reset"
}
```

**Response:**
```json
{
  "verification_token": "<token>",
  "message": "Code verified."
}
```

**Throttled:** 20 requests/minute

## Frontend email link landing

### `GET /email-auth-link`

Frontend-only landing page used by auth emails. The page reads `flow`, `source`, `email`, and `code` from the query string, then automatically calls one of the existing POST verification endpoints:

- `flow=auth` -> `POST /authn/email-auth/verify-code/`
- `flow=login` -> `POST /authn/login/verify-code/`
- `flow=register` -> `POST /authn/register/verify-code/`

On success it stores JWT credentials in the SPA and routes based on `source`.

## Password management

Both the authenticated **create/change-password** flow and the unauthenticated
**password-reset** flow verify the user through a recovery contact before a password is set.
Verification can happen over **email** (a hashed `EmailAuthChallenge` code) or, when no
verified email exists, **SMS** (the shared phone-OTP infrastructure). On a successful code
check, a one-time `verification_token` is minted (stored hashed on a `VERIFIED`
`EmailAuthChallenge` row) and consumed by the matching `confirm` step. The SMS channel reuses
the same token/confirm path — it is not a parallel mechanism — via a channel-aware
`EmailAuthChallenge` (`channel`, `target_phone` fields; see migration `0015`).

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

- **Response:** `{ "message": "...", "channel": "email" | "sms", "destination": "<masked>" }`
- Throttled per-user for both email and SMS sends; the SMS service also enforces a per-number cap.

### `POST /authn/change-password/verify-code/`

Authenticated. Body: `{ "code": "<6 digits>", "email": "<optional>" }`. Verifies the code on the
selected channel and returns `{ "message": "...", "verification_token": "...", "channel": "..." }`.

### `POST /authn/change-password/confirm/`

Authenticated. Body: `{ "verification_token", "new_password", "new_password_confirm", "key_id" }`.
Consumes the token (channel-agnostic) and sets the password. Unchanged by the SMS work.

> `POST /authn/change-password/` (the separate *current-password* change endpoint) is unchanged.

### Password reset (`POST /authn/password-reset/{request-code,verify-code,confirm}/`)

Unauthenticated, enumeration-safe. Accepts an `identifier` (email **or** phone; `email` kept as a
backward-compatible alias). The request step always returns the same generic message regardless of
whether an account exists. Verify/confirm return uniform `"Verification token is invalid or has
expired."` errors so the endpoint never reveals account existence. The public request endpoint
applies a per-IP SMS throttle when the identifier is a phone number.

## Token refresh

### `POST /authn/refresh/`

Standard SimpleJWT token refresh with rotation.

**Request:** `{ "refresh": "<token>" }`

**Response:** `{ "access": "<new_token>", "refresh": "<new_token>" }`

The old refresh token is blacklisted after rotation.

## Profile

### `GET /authn/profile/`

Returns the authenticated user's profile data.

### `PATCH /authn/profile/`

Updates profile fields. Supports `first_name`, `last_name`, `middle_name`, `organization`, `email_subscribe`, `profile_image`.

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

Updates a contact email (type, subscribe status).

### `DELETE /authn/contact-emails/{id}/`

Deletes a contact email, enforcing the recovery-contact policy atomically:

- Deletion is **blocked** (`409 Conflict`, actionable message) when removing the email would leave the
  member with **no verified recovery contact**. A verified phone or another verified email counts as a
  survivor; deleting an *unverified* email is always allowed. A phone-only account with a verified
  phone may therefore hold zero emails.
- If the deleted email was `primary`, another remaining email is promoted deterministically (prefer
  verified, else oldest). If no email remains, the account may have no primary.

### `POST /authn/contact-emails/{id}/verify/`

Initiates or completes email verification via challenge code.

### `POST /authn/contact-emails/{id}/make-primary/`

Promotes a verified contact email to primary (atomic; the previous primary is demoted).

## Contact phones

### `GET /authn/contact-phones/`

Lists the authenticated user's contact phones.

### `POST /authn/contact-phones/`

Creates a new contact phone. SMS verification is requested separately via `request-verification/`.

### `POST /authn/contact-phones/{id}/verify/`

Verifies phone with SMS OTP code (delivered via AWS SNS).

### `DELETE /authn/contact-phones/{id}/`

Deletes a contact phone. Enforces the **same** last-verified-recovery-contact rule as email deletion
(symmetric): removing a *verified* phone is blocked with **409** when it would leave the member with no
verified recovery contact (a verified email or another verified phone counts as a survivor). Deleting an
unverified phone is always allowed.

> Note: the unauthenticated **Subscribe** and **Event Registration** entry screens accept an email **or**
> a phone identifier (the existing passwordless code flows, `source=subscribe` / `event_registration`);
> the event ticket is still delivered to an email collected on the registration form.

## Account deletion

### `POST /authn/delete-account/`

Authenticated. Requires verification token from email challenge flow. Permanently deletes the member account.

## Auto-login endpoints

Token-based paths for email-originated actions:

| Endpoint | Token source | Service |
|----------|-------------|---------|
| `POST /authn/unsubscribe-login/` | Unsubscribe link in emails (no JWT; preference-only) | `src/apps/authn/views/` |
| `POST /mail/login-link/` | Login link in campaign and ticket emails (`LoginLinkToken`) | `src/apps/mail/views/login_link.py` |
| `POST /mail/magic-login/` | Legacy alias of `/mail/login-link/` for already-sent emails | `src/apps/mail/views/login_link.py` |

`/mail/login-link/` validates the token (validity frozen at send time; one-time by default, reusable per campaign/event opt-in) and returns JWT access/refresh tokens plus `redirect_to`.

## Admin invitation

### `POST /authn/admin-invite/accept/`

Accepts an admin invitation token and sets up the admin account.

## Mail system

The mail app (`src/apps/mail/`) handles email campaigns. Its only public API endpoint is the magic login above. Campaign management is done through Django admin — see [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md).

## Related pages

- [Architecture: Request Flow](../architecture/request-flow.md) — Login and token refresh sequences
- [Architecture: Frontend](../architecture/frontend.md) — Auth provider and crypto implementation
- [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md) — Email campaign admin
- [Routing Overview](routing-overview.md) — Full URL map

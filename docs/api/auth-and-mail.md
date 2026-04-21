# Auth & Mail API

Authentication, member management, contact information, and email-related endpoints.

## Overview

The auth system is built on `rest_framework_simplejwt` with custom extensions for email-based verification, RSA password encryption, and multiple auto-login paths. All auth endpoints live under `/authn/` except magic login (`/mail/magic-login/`).

## Code locations

| Concern | Path |
|---------|------|
| Views | `src/authn/views/` (subpackages: `auth/`, `account/`, `admin/`) |
| Serializers | `src/authn/serializers/` |
| Services | `src/authn/services/` |
| Models | `src/authn/models/` |
| URLs | `src/authn/urls.py` |
| Throttles | `src/authn/throttles.py` |
| Mail views | `src/mail/views.py` |

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

**Service:** `src/authn/services/create_member.py` (`CreateMemberService`)

## Login

### `POST /authn/login/`

Password-based login with RSA-encrypted password.

**Request:**
```json
{
  "email": "user@example.com",
  "encrypted_password": "<base64>",
  "key_id": "<uuid>"
}
```

**Response:**
```json
{
  "access": "<jwt>",
  "refresh": "<jwt>",
  "user": { "id": "<uuid>", "email": "...", "first_name": "...", ... },
  "requires_profile_completion": false
}
```

**Behavior:**
- Generic error message ("Invalid credentials.") regardless of whether email or password is wrong
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

### `POST /authn/password-reset/confirm/`

Completes password reset using a verification token from the email challenge flow.

### `POST /authn/change-password/`

Authenticated endpoint. Requires current password + verification token. Optionally blacklists the current refresh token and returns new tokens.

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

Creates a new contact email. Throttled: 5/hour.

### `PATCH /authn/contact-emails/{id}/`

Updates a contact email (type, subscribe status).

### `POST /authn/contact-emails/{id}/verify/`

Initiates or completes email verification via challenge code.

### `POST /authn/contact-emails/{id}/make-primary/`

Promotes a verified contact email to primary.

## Contact phones

### `GET /authn/contact-phones/`

Lists the authenticated user's contact phones.

### `POST /authn/contact-phones/`

Creates a new contact phone. Triggers SMS verification via Twilio.

### `POST /authn/contact-phones/{id}/verify/`

Verifies phone with Twilio Verify code.

## Account deletion

### `POST /authn/delete-account/`

Authenticated. Requires verification token from email challenge flow. Permanently deletes the member account.

## Auto-login endpoints

Three token-based login paths for email-originated actions:

| Endpoint | Token source | Service |
|----------|-------------|---------|
| `POST /authn/unsubscribe-login/` | Unsubscribe link in emails | `src/authn/views/auth/` |
| `POST /event/ticket-login/` | QR code on event ticket | `src/event/views/` |
| `POST /mail/magic-login/` | Magic link in campaign email | `src/mail/views.py` |

Each validates the token and returns JWT access/refresh tokens.

## Admin invitation

### `POST /authn/admin-invite/accept/`

Accepts an admin invitation token and sets up the admin account.

## Mail system

The mail app (`src/mail/`) handles email campaigns. Its only public API endpoint is the magic login above. Campaign management is done through Django admin — see [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md).

## Related pages

- [Architecture: Request Flow](../architecture/request-flow.md) — Login and token refresh sequences
- [Architecture: Frontend](../architecture/frontend.md) — Auth provider and crypto implementation
- [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md) — Email campaign admin
- [Routing Overview](routing-overview.md) — Full URL map

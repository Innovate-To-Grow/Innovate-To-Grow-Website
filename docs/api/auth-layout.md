# Authentication and Layout API

## Authentication

### Public endpoints

- `GET /authn/public-key/` returns the active RSA public key for password encryption.
- `POST /authn/register/` creates a pending member account and starts email verification.
- `POST /authn/login/` authenticates a member and returns access and refresh tokens.
- `POST /authn/login/request-code/` sends a one-time email login code.
- `POST /authn/login/verify-code/` verifies the login code and returns tokens.
- `POST /authn/register/verify-code/` finalizes email-based registration.
- `POST /authn/register/resend-code/` resends the registration code.
- `POST /authn/password-reset/request/` sends a password reset code.
- `POST /authn/password-reset/verify/` exchanges a code for a verification token.
- `POST /authn/password-reset/confirm/` sets a new password with the verification token.

### Authenticated endpoints

- `POST /authn/logout/` blacklists the refresh token.
- `GET /authn/profile/` returns the current member profile.
- `PATCH /authn/profile/` updates editable profile fields.
- `GET /authn/account-emails/` lists linked contact emails.
- `POST /authn/change-password/request-code/`, `/verify-code/`, and `/confirm/` handle in-session password changes.
- `POST /authn/contact-emails/` and `DELETE /authn/contact-emails/<id>/` manage contact emails.
- `POST /authn/contact-phones/` and `DELETE /authn/contact-phones/<id>/` manage contact phones.

## Auth flow details

1. Frontend fetches the RSA public key.
2. Passwords are encrypted with RSA-OAEP in the browser.
3. Django decrypts and validates credentials.
4. Access and refresh tokens are stored client-side.
5. The frontend refreshes tokens automatically on `401`.

## Layout

- `GET /layout/` returns menus, footer content, and `homepage_route`.
- `GET /sheets/<slug>/` returns the configured Google Sheets display payload.
- Layout data is cached in session storage and deduped across multiple React roots.

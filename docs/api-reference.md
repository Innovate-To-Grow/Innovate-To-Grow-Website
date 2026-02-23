# API Reference

Complete REST API reference for the Innovate To Grow backend.

## Base URL

| Environment | Base URL |
|------------|----------|
| Development | `http://localhost:8000` (Django dev server) |
| Development (via Vite proxy) | `http://localhost:5173/api` (strips `/api` prefix) |
| Production | Set via `VITE_API_BASE_URL` env var (CloudFront URL) |

## Authentication

Most endpoints are open (`AllowAny`). Authenticated endpoints require a JWT Bearer token:

```
Authorization: Bearer <access_token>
```

Passwords are RSA-encrypted on the client before transmission. See [Architecture — Authentication Flow](architecture.md#authentication-flow).

### Token Lifecycle

- **Access token**: 1-hour lifetime
- **Refresh token**: 7-day lifetime, rotated on each refresh
- **Header type**: `Bearer`

---

## Health Check

### `GET /health/`

Returns service health status. No authentication required.

**Response** `200`:
```json
{ "status": "ok" }
```

---

## Authn — Authentication (`/authn/`)

### `GET /authn/public-key/`

Returns the RSA public key for client-side password encryption.

- **Auth**: None

**Response** `200`:
```json
{
  "public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
  "key_id": "uuid-string"
}
```

### `POST /authn/register/`

Register a new member account. Passwords must be RSA-encrypted.

- **Auth**: None

**Request body**:
```json
{
  "email": "user@example.com",
  "password": "<base64-rsa-encrypted>",
  "password_confirm": "<base64-rsa-encrypted>",
  "key_id": "uuid-string"
}
```

**Response** `201`: Registration successful, verification email sent.

### `POST /authn/verify-email/`

Verify email address using the token from the verification email.

- **Auth**: None

**Request body**:
```json
{
  "token": "verification-token-string"
}
```

**Response** `200`: Email verified, returns user data and JWT tokens.

### `POST /authn/resend-verification/`

Resend the email verification link.

- **Auth**: None

**Request body**:
```json
{
  "email": "user@example.com"
}
```

### `POST /authn/login/`

Authenticate and receive JWT tokens. Password must be RSA-encrypted.

- **Auth**: None

**Request body**:
```json
{
  "email": "user@example.com",
  "password": "<base64-rsa-encrypted>",
  "key_id": "uuid-string"
}
```

**Response** `200`:
```json
{
  "access": "jwt-access-token",
  "refresh": "jwt-refresh-token",
  "user": {
    "member_uuid": "uuid",
    "email": "user@example.com",
    "display_name": "Name"
  }
}
```

### `POST /authn/refresh/`

Refresh an expired access token.

- **Auth**: None

**Request body**:
```json
{
  "refresh": "jwt-refresh-token"
}
```

**Response** `200`:
```json
{
  "access": "new-jwt-access-token",
  "refresh": "new-jwt-refresh-token"
}
```

### `GET /authn/profile/`

Retrieve the authenticated user's profile.

- **Auth**: Bearer token required

**Response** `200`:
```json
{
  "member_uuid": "uuid",
  "email": "user@example.com",
  "display_name": "Name"
}
```

### `PATCH /authn/profile/`

Update the authenticated user's display name.

- **Auth**: Bearer token required

**Request body**:
```json
{
  "display_name": "New Name"
}
```

---

## Pages — CMS Content (`/pages/`)

### `GET /pages/`

List all published pages (used by the menu editor).

- **Auth**: None

**Response** `200`: Array of page objects with `title`, `slug`, and metadata.

### `GET /pages/home/`

Retrieve the active home page with its components.

- **Auth**: None

**Response** `200`: Home page object with `components` array (ordered by placement).

### `GET /pages/<slug>/`

Retrieve a published page by its slug. Supports nested slugs (e.g., `legacy/about`).

- **Auth**: None

**Response** `200`: Page object with `components`, SEO fields, and analytics fields.
**Response** `404`: Page not found.

### `POST /pages/preview/validate-token/`

Validate an admin preview token.

- **Auth**: None (token-based validation)

**Request body**:
```json
{
  "token": "preview-token-string"
}
```

### `GET /pages/preview/data/`

Retrieve preview data pushed by the admin panel.

- **Auth**: None (token-based)

### `POST /pages/upload/`

Upload a media file to the asset library.

- **Auth**: Staff required

**Request**: `multipart/form-data` with `file` field.

**Response** `201`: MediaAsset object with `url`, `original_name`, `content_type`.

### `GET /pages/media/`

List all media assets in the library.

- **Auth**: Staff required

### `GET /pages/forms/<slug>/`

Retrieve a form definition by slug.

- **Auth**: None (respects form's `published` and `is_active` flags)

**Response** `200`: Form object with `fields` (JSON array of field definitions), `submit_button_text`, `success_message`.

### `POST /pages/forms/<slug>/submit/`

Submit data to a form.

- **Auth**: Depends on form settings (`login_required`, `allow_anonymous`)

**Request body**:
```json
{
  "field_name": "value",
  "another_field": "value"
}
```

**Response** `201`: Submission created.

### `GET /pages/forms/<form_slug>/submissions/`

List submissions for a form.

- **Auth**: Staff required

### `GET /pages/google-sheets/<sheet_id>/`

Fetch cached data from a Google Sheet.

- **Auth**: None (respects sheet's `is_enabled` flag)

**Response** `200`:
```json
{
  "headers": ["Column A", "Column B"],
  "rows": [["value1", "value2"], ...]
}
```

---

## Layout (`/layout/`)

### `GET /layout/`

Retrieve all layout data (menus and footer) in a single request.

- **Auth**: None

**Response** `200`: Object containing menu items and active footer content.

---

## Events (`/events/`)

### `GET /events/`

Retrieve the current published event with full schedule, winners, and tables.

- **Auth**: None

### `POST /events/sync/`

Import event data from Google Sheets. Performs an atomic full-replace of the specified sections.

- **Auth**: `X-API-Key` header required

See [Events Sheet Sync](events-sheet-sync.md) for full payload documentation.

### `GET /events/sync/export/`

Export event data in a sheet-friendly format. Supports full and delta modes.

- **Auth**: `X-API-Key` header required

**Query params**:
- `mode` — `full` (default) or `delta`
- `since` — ISO-8601 datetime (required for delta mode)

See [Events Sheet Sync](events-sheet-sync.md) for full response documentation.

### `POST /events/registration/request-link/`

Request a registration link sent via email/SMS.

- **Auth**: None

### `GET /events/registration/form/`

Retrieve the event registration form with ticket options and questions.

- **Auth**: Token-based (via registration link)

### `POST /events/registration/submit/`

Submit an event registration.

- **Auth**: Token-based (via registration link)

### `POST /events/registration/verify-otp/`

Verify an OTP code for event registration.

- **Auth**: None

### `GET /events/registration/status/`

Check registration status for a given token.

- **Auth**: Token-based

---

## Notify — Notifications (`/notify/`)

### `POST /notify/request-code/`

Request a verification code sent via email or SMS.

- **Auth**: None

**Request body**:
```json
{
  "email": "user@example.com"
}
```

### `POST /notify/request-link/`

Request a verification link sent via email.

- **Auth**: None

### `POST /notify/verify-code/`

Verify a received code.

- **Auth**: None

**Request body**:
```json
{
  "email": "user@example.com",
  "code": "123456"
}
```

### `GET /notify/verify-link/<token>/`

Verify a link token (clicked from email).

- **Auth**: None (token in URL)

### `POST /notify/send/`

Send a notification (email or SMS). Used internally by other services.

- **Auth**: Staff or internal

---

## MobileID (`/mobileid/`)

Uses DRF ViewSets with a `DefaultRouter`, providing standard CRUD operations.

### Barcodes — `/mobileid/barcodes/`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/mobileid/barcodes/` | List barcodes |
| `POST` | `/mobileid/barcodes/` | Create barcode |
| `GET` | `/mobileid/barcodes/<id>/` | Retrieve barcode |
| `PUT` | `/mobileid/barcodes/<id>/` | Update barcode |
| `PATCH` | `/mobileid/barcodes/<id>/` | Partial update |
| `DELETE` | `/mobileid/barcodes/<id>/` | Delete barcode |

### Mobile IDs — `/mobileid/mobile-ids/`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/mobileid/mobile-ids/` | List mobile IDs |
| `POST` | `/mobileid/mobile-ids/` | Create mobile ID |
| `GET` | `/mobileid/mobile-ids/<id>/` | Retrieve mobile ID |
| `PUT` | `/mobileid/mobile-ids/<id>/` | Update mobile ID |
| `PATCH` | `/mobileid/mobile-ids/<id>/` | Partial update |
| `DELETE` | `/mobileid/mobile-ids/<id>/` | Delete mobile ID |

### Transactions — `/mobileid/transactions/`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/mobileid/transactions/` | List transactions |
| `POST` | `/mobileid/transactions/` | Create transaction |
| `GET` | `/mobileid/transactions/<id>/` | Retrieve transaction |
| `PUT` | `/mobileid/transactions/<id>/` | Update transaction |
| `PATCH` | `/mobileid/transactions/<id>/` | Partial update |
| `DELETE` | `/mobileid/transactions/<id>/` | Delete transaction |

---

## Legacy Membership Routes

These routes provide backward-compatible event registration pages:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/membership/events` | Events listing page |
| `GET` | `/membership/events/<slug>` | Event detail page |
| `GET` | `/membership/event-registration/<slug>/<token>` | Registration form page |
| `GET` | `/membership/otp` | OTP entry page |
| `GET` | `/membership/otp/<token>` | OTP entry with pre-filled token |
| `GET` | `/membership/event-registration/status/<slug>/<token>` | Registration status check |

---

## Error Responses

All endpoints return standard HTTP status codes:

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `400` | Bad request / validation error |
| `401` | Authentication required |
| `403` | Permission denied |
| `404` | Not found |
| `500` | Server error |

Validation errors return field-specific messages:
```json
{
  "field_name": ["Error message."]
}
```

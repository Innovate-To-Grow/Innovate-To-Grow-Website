# Integration Points

External services the platform connects to, with references to implementation code.

## Google Sheets

Used for event registration data sync and schedule/project data import.

| Integration | Direction | Service file |
|-------------|-----------|-------------|
| Registration sheet sync | Django → Google Sheets (append rows) | `src/event/services/registration_sheet_sync.py` |
| Schedule sync | Google Sheets → Django (import tracks, projects) | `src/event/services/schedule_sync.py` |

**Authentication**: Google service account credentials stored in `GoogleCredentialConfig` model (`src/core/models/service_credentials.py`). The credential JSON is validated for required fields (`type`, `project_id`, `private_key`, `client_email`, `token_uri`).

**Libraries**: `gspread` 5.5.0, `google-auth` 2.35.0, `google-api-python-client` 2.170.0.

See [Google Sheets Integration](../integrations/google-sheets/index.md) for full details.

## AWS SES (Email)

Primary email delivery service in production.

| Concern | Implementation |
|---------|---------------|
| Configuration | `EmailServiceConfig` singleton in `src/core/models/service_credentials.py` |
| Campaign sending | `src/mail/services/send_campaign.py` |
| Auth challenge emails | `src/authn/services/email/send_email.py` |
| Ticket confirmation | `src/event/services/ticket_mail.py` |

`EmailServiceConfig` supports two backends:
1. **AWS SES** — access key, secret, region, from address, optional configuration set and SNS topic for bounce/complaint tracking
2. **SMTP fallback** — host, port, TLS, username, password

In development, `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` prints emails to stdout.

## Twilio (SMS)

Used for phone number verification during event registration and contact management.

| Concern | Implementation |
|---------|---------------|
| Configuration | `SMSServiceConfig` singleton in `src/core/models/service_credentials.py` |
| Send verification | `src/authn/services/sms/` |
| Event phone verify | `src/event/views/` (`SendPhoneCodeView`, `VerifyPhoneCodeView`) |

Uses the Twilio Verify API (not raw SMS). Credentials: `account_sid`, `auth_token`, `verify_sid`.

## AWS S3 / Cloudflare R2

File storage in production. Configured via `django-storages` with boto3.

| Concern | Setting |
|---------|---------|
| Static files | `STATICFILES_STORAGE` → S3 at `/static/` |
| Media files | `DEFAULT_FILE_STORAGE` → S3 at `/media/` |
| Bucket | `AWS_STORAGE_BUCKET_NAME` env var |
| Region | `AWS_S3_REGION_NAME` env var |
| Custom endpoint | `AWS_S3_ENDPOINT_URL` (for R2 compatibility) |

Configuration in `src/core/settings/components/production.py`.

## CKEditor 5

Rich text editing in Django admin for CMS blocks and email campaign bodies.

| Concern | Implementation |
|---------|---------------|
| Toolbar config | `src/core/settings/components/integrations/editor.py` |
| File uploads | `/ckeditor5/` URL path, staff-only permission |
| Storage | Uses the active file storage backend (local or S3) |

## RSS feeds (News sync)

The `sync_news` management command fetches articles from configured RSS feed sources.

| Concern | Implementation |
|---------|---------------|
| Feed sources | `NewsFeedSource` model in `src/cms/models/` |
| Sync service | `src/cms/management/commands/sync_news.py` |
| Sync logs | `NewsSyncLog` model tracks success/failure per sync |

## Third-party frontend services

Loaded via `<script>` tags in `pages/index.html`:

| Service | Purpose |
|---------|---------|
| UserWay | Accessibility widget |
| Site Improve Analytics | Usage analytics |
| Font Awesome 4.7 (CDN) | Icon library |

## Related pages

- [Google Sheets Integration](../integrations/google-sheets/index.md) — Detailed sync documentation
- [Deployment: Environments](../deployment/environments.md) — Environment variable reference
- [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md) — Email campaign operations

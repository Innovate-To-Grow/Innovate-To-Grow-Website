# Integration Points

External services the platform connects to, with references to implementation code.

## Google Sheets

Used for event registration data sync and schedule/project data import.

| Integration | Direction | Service file |
|-------------|-----------|-------------|
| Registration sheet sync | Django → Google Sheets (append rows) | `src/apps/event/services/registration_sheet_sync.py` |
| Schedule sync | Google Sheets → Django (import tracks, projects) | `src/apps/event/services/schedule_sync.py` |

**Authentication**: Google service account credentials stored in `GoogleCredentialConfig` model (`src/apps/core/models/service_credentials.py`). The credential JSON is validated for required fields (`type`, `project_id`, `private_key`, `client_email`, `token_uri`).

**Libraries**: `gspread` 5.5.0, `google-auth` 2.35.0, `google-api-python-client` 2.170.0.

See [Google Sheets Integration](../integrations/google-sheets/index.md) for full details.

## AWS shared credentials

A single IAM access key and AWS region power SES, SNS, and Bedrock. They are stored in `AWSCredentialConfig` (`src/apps/core/models/base/service_credentials/aws.py`) and resolved by `src/apps/core/services/aws/credentials.py`. The same admin page also holds the SNS origination phone number.

| Field | Used by |
|-------|--------|
| `access_key_id` / `secret_access_key` | SES, SNS, Bedrock |
| `default_region` | Shared AWS region for SES, SNS, and Bedrock |
| `sms_from_number` | SNS origination number for OTP SMS |

## AWS SES (Email)

Primary email delivery service in production.

| Concern | Implementation |
|---------|---------------|
| Email settings | `EmailServiceConfig` (`src/apps/core/models/base/service_credentials/email.py`) — sender address, campaign send rate, SMTP fallback |
| AWS credentials | Shared `AWSCredentialConfig` IAM key + `default_region` |
| Campaign sending | `src/apps/mail/services/send_campaign/` |
| Auth challenge emails | `src/apps/authn/services/email/send_email/` |
| Ticket confirmation | `src/apps/event/services/ticket_mail.py` |

Delivery uses AWS SES when an active `AWSCredentialConfig` is configured; otherwise it falls back to the SMTP fields on `EmailServiceConfig`. In development, `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` prints emails to stdout.

## AWS SNS (SMS)

Used for phone number verification during event registration and contact management.

| Concern | Implementation |
|---------|---------------|
| SMS settings | Shared `AWSCredentialConfig` IAM key + `default_region` + `sms_from_number` + OTP template |
| Send verification | `src/apps/authn/services/sms/sns_verify.py` |
| Event phone verify | `src/apps/event/views/registration/sms.py` (`SendPhoneCodeView`, `VerifyPhoneCodeView`) |

OTP codes are generated locally, stored in cache, and delivered via `sns:Publish`. Requires a registered SNS origination phone number on `AWSCredentialConfig.sms_from_number` and IAM permission `sns:Publish`.

## Amazon Bedrock (System Intelligence)

| Concern | Implementation |
|---------|---------------|
| AI behavior | `SystemIntelligenceConfig` (`src/apps/system_intelligence/models/config.py`) |
| AWS credentials | Shared `AWSCredentialConfig` IAM key + `default_region` |
| Runtime | `src/apps/core/services/bedrock/` |

## AWS S3 / Cloudflare R2

File storage in production. Configured via `django-storages` with boto3.

| Concern | Setting |
|---------|---------|
| Static files | `STATICFILES_STORAGE` → S3 at `/static/` |
| Media files | `DEFAULT_FILE_STORAGE` → S3 at `/media/` |
| Bucket | `AWS_STORAGE_BUCKET_NAME` env var |
| Region | `AWS_S3_REGION_NAME` env var |
| Custom endpoint | `AWS_S3_ENDPOINT_URL` (for R2 compatibility) |

Configuration in `src/config/settings/components/production.py`.

## CKEditor 5

Rich text editing in Django admin for CMS blocks and email campaign bodies.

| Concern | Implementation |
|---------|---------------|
| Toolbar config | `src/config/settings/components/integrations/editor.py` |
| File uploads | `/ckeditor5/` URL path, staff-only permission |
| Storage | Uses the active file storage backend (local or S3) |

## RSS feeds (News sync)

The `sync_news` management command fetches articles from configured RSS feed sources.

| Concern | Implementation |
|---------|---------------|
| Feed sources | `NewsFeedSource` model in `src/apps/cms/models/` |
| Sync service | `src/apps/cms/management/commands/sync_news.py` |
| Sync logs | `NewsSyncLog` model tracks success/failure per sync |

## Third-party frontend services

Loaded via `<script>` tags in `pages/index.html`:

| Service | Purpose |
|---------|---------|
| UserWay | Accessibility widget |
| Site Improve Analytics | Usage analytics |
| Font Awesome 4.7 (local vendor static) | Icon library |

## Related pages

- [Google Sheets Integration](../integrations/google-sheets/index.md) — Detailed sync documentation
- [Deployment: Environments](../deployment/environments.md) — Environment variable reference
- [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md) — Email campaign operations

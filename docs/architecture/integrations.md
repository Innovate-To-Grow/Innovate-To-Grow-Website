# Integration Points

External services the platform connects to, with references to implementation code.

## Google Sheets

Used for event registration data sync and schedule/project data import.

| Integration | Direction | Service file |
|-------------|-----------|-------------|
| Registration sheet sync | PostgreSQL outbox worker → Google Sheets (managed-cell reconciliation) | `src/apps/event/services/registration_sheet_sync/` |
| Schedule sync | Google Sheets → Django (import tracks, projects) | `src/apps/event/services/schedule_sync/` |

**Authentication**: Google service account credentials are stored in
`GoogleCredentialConfig`
(`src/apps/core/models/base/service_credentials/google.py`). The credential
JSON is validated for required fields (`type`, `project_id`, `private_key`,
`client_email`, `token_uri`).

**Libraries**: `gspread` 6.2.1, `google-auth` 2.56.2,
`google-api-python-client` 2.198.0.

See [Google Sheets Integration](../integrations/google-sheets/index.md) for full details.

## AWS shared credentials

A single IAM credential pair in AWS Secrets Manager powers SES, SMS (End User Messaging), and Bedrock. `AWSCredentialConfig` stores its `credentials_secret_arn`, region, and service metadata. The shared resolver in `src/apps/core/services/aws/credentials.py` reads the secret with the ECS task identity; production rejects database plaintext fallback. See the [production migration procedure](../deployment/production.md#application-aws-credentials-and-background-jobs).

| Field | Used by |
|-------|--------|
| `credentials_secret_arn` | Reference to the secret JSON containing `access_key_id` / `secret_access_key` for SES, SMS, and Bedrock |
| `default_region` | Shared AWS region for SES, SMS, and Bedrock |
| `sms_from_number` | SMS origination number for OTP SMS (optional override; auto-detected from End User Messaging when blank) |

**Required infra change for Smart rate (delivery-rate discovery).** Smart rate reads the account's sending limits with this same credential. It needs `ses:GetAccount`, which gives the SES rate and 24-hour quota and whether sending is paused. It also needs `sms-voice:DescribePhoneNumbers` (already required, below), `sms-voice:DescribeSenderIds` and `sms-voice:DescribeSpendLimits`, which give the number's message parts per second and the monthly spend limit. The credential's IAM policy lives outside this repository: `aws/cicd/identity-stack.json` grants the ECS task role only the Secrets Manager and Amplify actions, so grant these four read-only actions to the IAM user behind `credentials_secret_arn`. Until `ses:GetAccount` is granted, Smart rate bounds SES by the provider limit that migration `core.0036` seeded from the active email config's campaign send rate, or by the 1 recipient/sec sandbox fallback when that rate was 0.

## Email delivery (AWS SES, SMTP, or Microsoft Graph)

The application has one globally active email provider at a time. Administrators
select AWS SES, SMTP, or Microsoft Graph under **Mail → Notification Delivery**;
authentication, tickets, campaigns, inbox replies, and test messages all use that
selection. There is no per-message routing or automatic failover.

| Concern | Implementation |
|---------|---------------|
| Email settings | `EmailServiceConfig` (`src/apps/core/models/base/service_credentials/email.py`) — active sender identity, selected provider, and campaign send rate |
| AWS credentials | Shared `AWSCredentialConfig` Secrets Manager reference + `default_region` |
| SMTP credentials | Active `SMTPProviderConfig` host, port, TLS/SSL, optional authentication, and timeout |
| Microsoft Graph credentials | Active `MicrosoftGraphProviderConfig` (`src/apps/core/models/base/service_credentials/microsoft_graph.py`) — Entra tenant ID, client ID, optional sender mailbox, and messages per minute; its current certificate (`MicrosoftGraphCertificate`) pins the private key's version in the credential store (AWS Secrets Manager in production). Certificate authentication only |
| Provider layer | `src/apps/core/services/email/` (SES in `ses.py`, SMTP in `smtp.py`, Microsoft Graph in `graph/`) |
| Campaign sending | `src/apps/mail/services/send_campaign/` |
| Auth challenge emails | `src/apps/authn/services/email/send_email/` |
| Ticket confirmation | `src/apps/event/services/ticket/mail.py` |

Microsoft Graph sends each message as base64 MIME with `POST /users/{mailbox}/sendMail`,
authenticated by an app-only access token (OAuth 2.0 client-credentials flow).
A message that carries a credential (`EmailMessage(keep_sent_copy=False)`: verification
codes, admin invitations, tickets, and campaign messages that contain the recipient's
`{{login_link}}`) is sent in Graph's JSON format with `saveToSentItems: false` instead,
so no copy stays in the mailbox's Sent Items (such a campaign message then has no
`List-Unsubscribe` header, only the footer link).
Tokens are cached in process memory only, never in the database or the shared cache.
The private key is never in the database: a superuser installs the certificate on the
Graph configuration's admin page, the key goes to the credential store
(`apps.core.services.credential_store`; in production the Secrets Manager secret
`itg/backend/microsoft-graph/certificate-key`, which the task role may write), and the
`MicrosoftGraphCertificate` row pins its version. The Graph transport refuses every
request except the token request, `sendMail` and three read-only GETs before
connecting. Graph answers `202 Accepted` with no message ID, so the MIME `Message-ID`
is recorded instead. With read permission on the sending mailbox, the admin inbox
(**Mail → Inbox**) reads that mailbox through Graph instead of Gmail IMAP.

`verify_graph_access` (or **Run access check** in the admin) asks Microsoft what the
app may do, compares it with the approved roles and mailbox scope, and records a
`MicrosoftGraphAccessCheck` row. In production (`GRAPH_REQUIRE_ACCESS_EVIDENCE`)
email can switch to Graph only with a recent passing check for the current
certificate, and email already on Graph can move to another Graph configuration or
Entra app only on the same terms (`takeover_problem`). See [Microsoft Graph email](../integrations/microsoft-graph-email.md) for
the Microsoft-side setup, key storage, validation, limits, and error reference.

Delivery fails closed unless the selected provider and sender are structurally
configured. A failed or uncertain request is never retried through the other
provider. Jobs resolve the active provider when execution begins, so queued work
that has not started follows the current global selection.

Verification emails with uncertain provider acceptance retain their pending
challenge and continue to code entry. The normal code hash, expiry, attempt
limit, and resend limits still apply; no authentication is granted until the
code is verified.

SES Configuration Set and SNS delivery-event tracking remain SES-specific.
Campaigns include recipient and attempt tags so configuration-set events can
be recorded even before the send response returns. Older untagged messages
continue to match by their saved provider message ID.
SMTP and Microsoft Graph record successful submission acceptance only (for Graph,
an HTTP 202); they do not claim delivered, bounced, or complained status without a
future feedback integration. Graph's later non-delivery reports arrive in the
sender mailbox; the admin inbox can show them, but nothing parses them. The SES
account-level suppression list applies only to SES sends, and the application keeps
no suppression list of its own, so under SMTP or Graph previously bounced or
complaining addresses are mailed again.

## AWS End User Messaging (SMS)

Used for phone number verification during event registration and contact management.

| Concern | Implementation |
|---------|---------------|
| SMS settings | Shared `AWSCredentialConfig` Secrets Manager reference + `default_region` + optional `sms_from_number` override + OTP template |
| Origination resolution | `src/apps/core/services/aws/sms.py` (`describe_phone_numbers`, cached) |
| Sending | `src/apps/core/services/aws/sms_send.py` (`send_text_message`, the only `SendTextMessage` call, paced by the delivery-rate limiter) |
| Send verification | `src/apps/authn/services/sms/` (`sns_verify.py` is the public entry point; `checks.py` holds the code checks, `errors.py` the error types) |
| Event phone verify | `src/apps/event/views/registration/sms.py` (`SendPhoneCodeView`, `VerifyPhoneCodeView`) |

OTP codes are generated locally, stored only as hashes in
`PhoneVerificationChallenge`, and delivered via AWS End User Messaging
(`pinpoint-sms-voice-v2:SendTextMessage`). Challenges are bound to purpose,
phone, optional member, and context, with persistent attempt/send limits and
one-time consumption. The origination number is auto-detected from the
account's End User Messaging phone numbers (`DescribePhoneNumbers`), or set
manually via `AWSCredentialConfig.sms_from_number`. Requires IAM permissions
`sms-voice:SendTextMessage` and `sms-voice:DescribePhoneNumbers`.

Every SMS (codes, the admin test SMS, campaigns) is sent by `send_text_message` on the `sms_send` delivery
channel, for the identity `<region>:<origination>`; the SendTextMessage quota is per account and Region, so a
throttle pauses every number of the Region. AWS's answer is matched against `DELIVERY_RATES["signals"]["sms"]`:
`ThrottlingException` slows the channel down, `ServiceQuotaExceededException` with the reason
`MONTHLY_SPEND_LIMIT_REACHED_FOR_TEXT` stops all SMS until the hourly probe (or a raised spend limit), and a
disabled account or a missing origination identity stops it until fixed. An OTP takes its slot before it locks the
number or reserves anything, so SMS delivery held back answers `PhoneVerificationBusy` (HTTP 503 with
`Retry-After`, "SMS delivery is busy right now; please try again in about N seconds.") without spending the
number's hourly cap or the daily SMS budget. `PhoneVerificationThrottled` (429) stays the per-number cap. A queued
campaign recipient held back runs again at its slot; the in-process sender retries a throttled recipient after the
cooldown and pauses the rest on a long hold ("Resume paused recipients" on the SMS campaign admin).

### Gmail IMAP (admin inbox, Import from Gmail)

Each uncached Gmail read is one IMAP login session on the `gmail_imap` delivery channel for
`<imap host>:<username>` (`src/apps/mail/services/gmail_import/session.py`), connected with
`channels.gmail_imap.timeout_seconds`. Google publishes no IMAP rate, so the channel only reacts to Gmail's
answers (`DELIVERY_RATES["signals"]["imap"]`): "Too many simultaneous connections" pauses reads, a bandwidth
suspension (`[OVERQUOTA]`) stops them for `bandwidth_breaker_seconds` with no connection attempted, `[UNAVAILABLE]`
and a login marked `[THROTTLED]` slow them down, and refused credentials stop them until the Gmail account is saved.
While reads are held back the inbox list shows the last list read with a banner, and Import from Gmail says when to
try again. A cached list or message never takes a slot.

## Amazon Bedrock (System Intelligence)

| Concern | Implementation |
|---------|---------------|
| AI behavior | `SystemIntelligenceConfig` (`src/apps/system_intelligence/models/config.py`) |
| Public spend limits | Per-visitor/member and global token budgets in PostgreSQL, set on the same config; see [Assistant and AI search limits](../integrations/assistant-limits.md) |
| AWS credentials | Shared `AWSCredentialConfig` Secrets Manager reference + `default_region` |
| Runtime | `src/apps/system_intelligence/services/bedrock/` |

Known Claude models with fixed sampling (including Fable 5) omit `temperature` in both Converse and agent calls. Older models retain the configured value. The admin connectivity test also omits optional sampling settings and reads text after any reasoning blocks. See [Anthropic sampling limits](https://platform.claude.com/docs/en/about-claude/models/extended-thinking-models).

## AWS S3 / Cloudflare R2

File storage in production. Configured via `django-storages` with boto3.

| Concern | Setting |
|---------|---------|
| Static files | `STATICFILES_STORAGE` → S3 at `/static/` |
| Media files | `DEFAULT_FILE_STORAGE` → S3 at `/media/` |
| Bucket | `AWS_STORAGE_BUCKET_NAME` env var |
| Region | `AWS_S3_REGION_NAME` env var |
| Custom endpoint | `AWS_S3_ENDPOINT_URL` (for R2 compatibility) |

Configuration in `src/config/settings/production/storage.py`.

## CKEditor 5

Rich text editing in Django admin for CMS blocks and email campaign bodies.

| Concern | Implementation |
|---------|---------------|
| Toolbar config | `src/config/settings/base/integrations/editor/__init__.py` |
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
- [Microsoft Graph email](../integrations/microsoft-graph-email.md) — Entra app setup, mailbox scoping, limits, and errors for the Graph email provider
- [Deployment: Environments](../deployment/environments.md) — Environment variable reference
- [CMS & Admin: Member & Mail Tools](../cms-admin/member-and-mail-tools.md) — Email campaign operations

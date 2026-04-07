# Member & Mail Tools

Member management, email campaigns, and contact administration.

## Member management

### Member model

`Member` (`src/authn/models/member.py`) extends Django's `AbstractUser` with `ProjectControlModel` (UUID PK). Key fields:

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Primary key (not auto-increment) |
| `email` | EmailField | Primary login identifier |
| `first_name`, `last_name` | CharField | Required |
| `middle_name` | CharField | Optional |
| `organization` | CharField | Optional |
| `email_subscribe` | BooleanField | Newsletter opt-in |
| `profile_image` | ImageField | Profile photo |

### Admin capabilities

In Django admin → Members & Auth → Members:
- Search by name, email
- Filter by active status, subscription, date joined
- Inline contact emails and phones
- Import/export members via Excel (openpyxl)

### Contact information

Members can have multiple contact emails and phones:

- **ContactEmail**: Types (primary, secondary, other), verified flag, subscribe flag
- **ContactPhone**: Region support, verified flag, subscribe flag

Contact verification uses the email challenge system or Twilio SMS.

### Admin invitations

`AdminInvitation` allows existing staff to invite new admin users:
1. Staff creates an invitation with the invitee's email
2. System sends an invitation email with a token
3. Invitee follows the link to set up their admin account

## Email campaigns

### Overview

The mail app (`src/mail/`) provides email campaign functionality through Django admin. Campaigns are composed in the admin using CKEditor 5 and sent to selected audiences.

### Campaign model

`EmailCampaign` (`src/mail/models/campaign.py`):

| Field | Purpose |
|-------|---------|
| `subject` | Email subject line |
| `body` | HTML body (CKEditor 5) |
| `audience_type` | Target audience selector |
| `status` | `draft`, `sending`, `sent`, `failed` |
| `total_recipients` | Calculated recipient count |
| `sent_count` | Successfully sent count |

### Audience types

| Type | Recipients |
|------|-----------|
| `subscribers` | Members with `email_subscribe = True` |
| `event_registrants` | Members registered for a specific event |
| `selected_members` | Manually selected members (ManyToMany) |
| `manual` | Comma-separated email addresses |
| `ticket_type` | Registrants with a specific ticket type |
| `checked_in` | Registrants who checked in to an event |
| `not_checked_in` | Registrants who did not check in |
| `all_members` | All active members |
| `staff` | Staff users only |

Audience resolution is handled by `src/mail/services/audience.py`.

### Personalization

`src/mail/services/personalize.py` supports template variables in the email body:

| Variable | Replaced with |
|----------|--------------|
| `{{ first_name }}` | Recipient's first name |
| `{{ organization }}` | Recipient's organization |
| `{{ unsubscribe_link }}` | Auto-login unsubscribe URL |

### Sending

`src/mail/services/send_campaign.py`:

1. Resolves audience to recipient list
2. Personalizes the body for each recipient
3. Sends via active `EmailServiceConfig` (AWS SES primary, SMTP fallback)
4. Logs each send attempt in `RecipientLog`
5. Updates campaign `sent_count` and `status`

### Magic login tokens

`MagicLoginToken` (`src/mail/models/magic_login.py`) enables one-click login from campaign emails. When a personalized email includes a magic link, clicking it authenticates the user via `POST /mail/magic-login/`.

### Gmail import

The campaign admin includes a Gmail import feature (`src/mail/services/gmail_import.py`) that can fetch email templates from a Gmail account for use as campaign bodies.

### Recipient logs

`RecipientLog` (`src/mail/models/recipient_log.py`) tracks per-recipient delivery:

| Field | Purpose |
|-------|---------|
| `campaign` | FK to EmailCampaign |
| `email` | Recipient email address |
| `status` | Delivery status |
| `sent_at` | Timestamp |
| `error` | Error message if failed |

Viewable as inline records in the campaign admin.

## Related pages

- [Django Admin](django-admin.md) — Admin interface and customization
- [API: Auth & Mail](../api/auth-and-mail.md) — Auth and mail API endpoints
- [Architecture: Integrations](../architecture/integrations.md) — AWS SES and Twilio configuration
- [Operations](operations.md) — Operational tasks

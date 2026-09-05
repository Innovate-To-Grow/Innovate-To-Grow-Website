# Member & Mail Tools

Member management, email campaigns, and contact administration.

## Member management

### Member model

`Member` (`src/apps/authn/models/member.py`) extends Django's `AbstractUser` with `ProjectControlModel` (UUID PK). Key fields:

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

Contact verification uses the email challenge system or AWS SNS SMS.

### Admin invitations

`AdminInvitation` allows existing staff to invite new admin users:
1. Staff creates an invitation with the invitee's email
2. System sends an invitation email with a token
3. Invitee follows the link to set up their admin account

## Email campaigns

### Overview

The mail app (`src/apps/mail/`) provides email campaign functionality through Django admin. Campaigns are composed in the admin using CKEditor 5 and sent to selected audiences.

### Campaign model

`EmailCampaign` (`src/apps/mail/models/campaign.py`):

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

Audience resolution is handled by `src/apps/mail/services/audience.py`.

### Personalization

`src/apps/mail/services/personalize.py` supports template variables in the email body:

| Variable | Replaced with |
|----------|--------------|
| `{{ first_name }}` | Recipient's first name |
| `{{ organization }}` | Recipient's organization |
| `{{ unsubscribe_link }}` | Auto-login unsubscribe URL |

### Sending

`src/apps/mail/services/` and the PostgreSQL outbox:

1. Resolve the audience and materialize one recipient log plus one durable job
   per recipient
2. Personalize the body for each recipient
3. Resolve the single globally active provider (AWS SES or SMTP) and submit through the shared provider-neutral service
4. Persist processing, retry, failed, and uncertain-delivery state per
   recipient
5. Aggregate campaign state/counts from the recipient logs

Provider calls whose outcome cannot be determined are marked `uncertain` and
are never resent automatically. Reconcile provider evidence before using the
explicit admin retry action.

Switching providers is global and does not configure failover. SES campaign
delivery, bounce, and complaint events remain available only for messages sent
through SES. SMTP campaigns record submission acceptance as `sent`; no later
delivery status is inferred without an SMTP feedback integration.

### Login link tokens

`LoginLinkToken` (`src/apps/mail/models/login_link.py`) is the single mechanism behind emailed one-click login links — both campaign `{{login_link}}` links and the login button in event ticket confirmation emails. Clicking a link authenticates the user via `POST /mail/login-link/` (legacy alias: `/mail/magic-login/`) and redirects to the configured destination (campaign `login_redirect_path`, or the per-token path — `/event-registration?event=<event-slug>` for ticket links).

Policy is configured at the issuing source and enforced per token:

- **Validity** — `EmailCampaign.login_link_validity_days` (default 7) / `Event.ticket_login_validity_days` (default 30), 1–90 days, frozen onto each token at send time.
- **Reuse** — `EmailCampaign.login_link_reusable` (default off) / `Event.ticket_login_reusable` (default on). Read live at login time, so unticking the flag immediately blocks further reuse of already-used links — a kill switch.
- **Revocation** — admin actions on Broadcast Email (campaign), Event Registrations, and the read-only **Login Links** changelist (`/admin/mail/loginlinktoken/`) expire tokens immediately. The raw token value is never displayed in admin.

Resending a ticket email revokes the registration's previous link before issuing a new one.

### Gmail import

The campaign admin includes a Gmail import feature (`src/apps/mail/services/gmail_import.py`) that can fetch email templates from a Gmail account for use as campaign bodies.

### Recipient logs

`RecipientLog` (`src/apps/mail/models/recipient_log.py`) tracks per-recipient delivery:

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
- [Architecture: Integrations](../architecture/integrations.md) — AWS SES and AWS SNS configuration
- [Operations](operations.md) — Operational tasks

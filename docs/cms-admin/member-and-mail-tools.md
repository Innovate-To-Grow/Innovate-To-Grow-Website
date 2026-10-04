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
| `profile_image` | ImageField | Profile photo |

There is no member-level subscription field: newsletter subscription is the `subscribe` flag of each contact email
(below). The profile API's `email_subscribe` is the primary contact email's flag.

### Admin capabilities

In Django admin → Members & Auth → Members:
- Search by name, email
- Filter by active status, staff status, date joined (subscription is filtered per address in the Contact Emails admin)
- Inline contact emails and phones
- Import/export members via Excel (openpyxl)

### Contact information

Members can have multiple contact emails and phones:

- **ContactEmail**: Types (primary, secondary, other), verified flag, and a per-address `subscribe` flag (on by
  default). That flag is the only thing that decides whether the address receives newsletters (see
  [Audience types](#audience-types)); `verified` plays no part in it
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

### Choose the email sender

Open **Mail → Notification Delivery → Edit Notification Delivery**. Under
**Email Sender**, select **AWS SES** or **SMTP**, set the sender name and email
address, and save the active configuration.

- **AWS SES** uses the active AWS credentials and region. SMTP fields are not
  required, and any saved SMTP credentials are preserved when selecting SES.
- **SMTP** shows the server, port, security, and optional authentication fields.
  Leave the password blank when editing to retain the saved password. STARTTLS
  and SSL both verify the server certificate; enable only one of them.
- AWS settings remain available for SMS even when email uses SMTP. Changing the
  email provider does not switch the SMS provider.

This selection applies to verification codes, admin invitations, tickets,
campaigns, inbox replies, and the **Send Test Email** action. Saving settings
does not send a message; use the test action to check delivery explicitly.

### Campaign model

`EmailCampaign` (`src/apps/mail/models/campaign.py`):

| Field | Purpose |
|-------|---------|
| `subject` | Email subject line |
| `body` | HTML body (CKEditor 5) |
| `audience_type` | Target audience selector |
| `member_email_scope` | **Send to**: each member's primary contact email only, or every contact email (member-based audiences) |
| `include_unsubscribe_header` | **Include one-click unsubscribe** (default on): the footer unsubscribe link and the RFC 8058 `List-Unsubscribe` headers |
| `status` | `draft`, `sending`, `sent`, `failed` |
| `total_recipients` | Calculated recipient count |
| `sent_count` | Successfully sent count |

### Audience types

| Type | Recipients |
|------|-----------|
| `subscribers` | All Email Subscribers: active members, at their subscribed addresses only (below) |
| `event_registrants` | Members registered for a specific event |
| `selected_members` | Manually selected members (ManyToMany) |
| `manual` | Comma-separated email addresses |
| `ticket_type` | Registrants with a specific ticket type |
| `checked_in` | Registrants who checked in to an event |
| `not_checked_in` | Registrants who did not check in |
| `all_members` | All active members |
| `staff` | Staff users only |

Audience resolution is handled by `src/apps/mail/services/audience/` (`resolvers.py`). The recipient list is resolved
once, when sending starts (with the background worker, when the campaign is queued), so an address unsubscribed after
that still receives that campaign.

**All Email Subscribers.** The per-address `subscribe` flag is authoritative. Only members with `is_active` set are
included, and each is mailed only at addresses whose own flag is on:

- **Send to: primary only** — the primary address, and only if it is subscribed. A subscribed secondary address
  does not stand in for an unsubscribed primary; such a member gets nothing.
- **Send to: all emails** — every subscribed address (primary, secondary, other).

`verified` is not required. The member import creates addresses unverified and subscribed unless the sheet says
otherwise, so requiring verification would drop most of the mailing list. The one-click unsubscribe link turns off
every address of the member at once (see
[Auth & Mail](../api/auth-and-mail.md#one-click-unsubscribe-and-resubscribe)); members change single addresses on
`/account`. When **Exclude audience** is All Email Subscribers, the same rules build the exclusion list with the
exclude **Send to** setting. The campaign form's **Send to** help text states these rules too.

**Change from the old primary-only rule.** The audience used to take every member whose primary address was
subscribed and, with **Send to: all emails**, mail all of that member's addresses whatever their own flags; the
one-click link and the `/account` primary toggle cleared only the primary. The data migration
`mail.0019_carry_primary_opt_out_to_all_addresses` (it runs with the deploy's `migrate`) turns off the other addresses
of every member whose primary is unsubscribed, so nobody who opted out that way is mailed again. Compared with the old
rule, the audience shrinks by inactive members and by addresses whose own flag is off (with **Send to: all emails**),
and grows by members who have no primary address at all, a legacy gap: they are now mailed at their subscribed
addresses with **Send to: all emails**. An address an event registration adds to an account is subscribed only while
another address of the member is.

**Open product question: the other audiences ignore the flag.** Only All Email Subscribers reads `subscribe`. All
Active Members, Staff Members and Selected Members mail the primary (or every) address of each member, and the
event-based audiences mail the attendee or primary address, whether or not it is subscribed. Those emails still carry
the unsubscribe link and header when **Include one-click unsubscribe** is on, so a person who unsubscribed keeps
receiving them, and clicking that link does not stop them. The unsubscribe pages and confirmation email say only
newsletters stop ("You may still receive account messages, messages about events you registered for, and program
announcements"). Whether those audiences should honour the flag, or leave out the unsubscribe link, is undecided.

### Personalization

`src/apps/mail/services/campaign/personalize.py` replaces these placeholders in the subject and body (plain string
replacement, `{{name}}` or `{{ name }}`):

| Variable | Replaced with |
|----------|--------------|
| `{{ first_name }}`, `{{ last_name }}`, `{{ full_name }}` | Recipient's name (for event-based audiences, the registration's attendee name when set) |
| `{{ login_link }}` | The recipient's login link (see [Login link tokens](#login-link-tokens)); empty for manual addresses |

There is no unsubscribe placeholder. With **Include one-click unsubscribe** on, every email to a member (any
audience) gets an "Unsubscribe from newsletters" link in the footer and the RFC 8058 `List-Unsubscribe` /
`List-Unsubscribe-Post` headers, both pointing at the backend page `/mail/unsubscribe/{token}/` (valid 365 days; see
[Auth & Mail](../api/auth-and-mail.md#one-click-unsubscribe-and-resubscribe)). Manual addresses get neither, and
nothing is added while `BACKEND_URL` is unset. The admin preview shows a placeholder link.

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
are never resent automatically. A verified SES event for the same send attempt
resolves the recipient and its background job together, clearing the uncertainty
from worker monitoring without another send. Otherwise, reconcile provider
evidence before using the explicit admin retry action.

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

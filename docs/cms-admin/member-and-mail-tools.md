# Member & Mail Tools

Member management, email campaigns, and contact administration.

## Member management

### Member model

`Member` (`src/apps/authn/models/members/member.py`) extends Django's `AbstractUser` with `ProjectControlModel` (UUID PK). Key fields:

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
**Email Sender**, select **AWS SES**, **SMTP**, **Microsoft Graph**, or **Gmail API**, set the
sender name and email address, and save the active configuration.

- **AWS SES** uses the active AWS credentials and region. SMTP and Microsoft
  Graph fields are not required, and any saved SMTP or Graph credentials are
  preserved when selecting SES.
- **SMTP** shows the server, port, security, and optional authentication fields.
  Leave the password blank when editing to retain the saved password. STARTTLS
  and SSL both verify the server certificate; enable only one of them.
- **Microsoft Graph** shows the active Graph configuration read-only: tenant
  ID, client ID, sender mailbox, the installed
  certificate's SHA-1 thumbprint and expiry, and the **mailbox scope** (the
  mailboxes Graph may use and each one's permission level: send, read, or
  both). This page only selects Graph; the configuration, its scope and its
  certificate are managed on the Graph configuration's admin page (Core app,
  linked from the panel for staff who have it), and must be in place before
  Graph can be selected. In production Graph can be selected only after a
  superuser has run the access check with the current certificate and it
  matched the approval (the panel's **Go-live evidence** line says what is
  missing; see [Validate the access restriction](../integrations/microsoft-graph-email.md#validate-the-access-restriction)).
  Graph authenticates with a certificate only; a
  superuser installs it there, and its private key is kept in the credential
  store, never in the database. The sender mailbox
  defaults to the From email; both must be in the scope with send permission.
  With read permission, **Mail → Inbox** reads that mailbox through Graph
  instead of the Gmail import account; its **Sent** folder (and any message
  from the site's own address) is then shown to superusers only, and Sent
  mail is never sent to the AI scam review. Opening an Inbox message whose
  rule score is in the medium band still sends its sender, subject,
  authentication results and the first 4,000 characters of its body to
  Amazon Bedrock for a second opinion (see
  [Admin inbox](../integrations/microsoft-graph-email.md#admin-inbox)).
  Graph mail counts against the
  mailbox's Exchange Online limits (its rate is on **Mail → Delivery Rates**) and reports
  no delivery events. Campaigns, replies and notices are copied to its Sent
  Items folder; verification codes, admin invitations, tickets and campaign
  messages that contain the recipient's `{{ login_link }}` are not, because
  they carry sign-in credentials. A campaign message with a login link then
  has no `List-Unsubscribe` header (Graph cannot send one without the copy);
  its footer's unsubscribe link stays.
  Setup in Entra and Exchange Online is in
  [Microsoft Graph email](../integrations/microsoft-graph-email.md).
- **Gmail API** shows the active Gmail API configuration read-only: its key
  ID, service account, numeric client ID, project, when the key was installed
  and the access check last passed, and the **account allow-list** (the Google
  accounts the site may send as). There are no credential fields here: the key
  and the list are managed by a superuser on the configuration's own page. The
  From email must be on the list, and email can switch to the Gmail API (or
  change its From address there) only after the access check passed for the
  installed key. Gmail keeps a copy of everything it sends in the account's Sent
  folder: mail with sign-in codes or login links is tagged and never shown by
  **Mail → Inbox** or **Import from Gmail**, and the inbox's **Sent** folder is
  shown to superusers only while the Gmail import account is one the site sends
  as. Rates and daily limits are on **Mail → Delivery Rates**. Setup:
  [Gmail API email](../integrations/gmail-api-email.md).
- AWS settings remain available for SMS even when email uses SMTP, Microsoft
  Graph or the Gmail API. Changing the email provider does not switch the SMS provider.

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
| `status` | `draft`, `queued`, `sending`, `partial` (Partially sent: some recipients failed or are paused), `sent`, `failed` |
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
3. Resolve the single globally active provider (AWS SES, SMTP, Microsoft Graph, or the Gmail API) and submit through the shared provider-neutral service
4. Persist processing, retry, failed, and uncertain-delivery state per
   recipient
5. Aggregate campaign state/counts from the recipient logs

A recipient the delivery-rate limiter holds back is not sent and not failed: a
queued recipient runs again at its slot without using an attempt, and the
in-process sender (no background worker) marks the remaining recipients
**Paused by delivery limits** on a long hold, such as a daily limit or a provider
stop, and ends the campaign **Partially sent**. The **Resume paused recipients
(held back by delivery limits)** action on the Email Campaigns and SMS Campaigns
lists sends exactly those later, through the queue when background jobs are
enabled; it leaves a campaign that is still sending or queued alone. See
[Delivery rates](../integrations/delivery-rates.md#waiting-deferral-and-the-background-worker).

Provider calls whose outcome cannot be determined are marked `uncertain` and
are never resent automatically. A verified SES event for the same send attempt
resolves the recipient and its background job together, clearing the uncertainty
from worker monitoring without another send. Otherwise, reconcile provider
evidence before using the explicit admin retry action.

Switching providers is global and does not configure failover. SES campaign
delivery, bounce, and complaint events remain available only for messages sent
through SES. SMTP and Microsoft Graph campaigns record submission acceptance as
`sent` (for Graph, an HTTP 202 from `sendMail`); no later delivery status is
inferred without a feedback integration. Graph's non-delivery reports arrive in
the sender mailbox, not in the application, and its uncertain outcomes are
explained in the
[error reference](../integrations/microsoft-graph-email.md#error-reference). The
Delivery Dashboard under **Delivery Operations** charts SES CloudWatch metrics
only and shows a notice while another provider is active.

### Delivery rates

**Mail → Delivery Operations → Delivery Rates** (`/admin/mail/settings/rates/`, staff with the Mail app) sets how
fast the site sends and reads, with one card per channel: the four email providers (the one selected under
Notification Delivery first, the others under **Not in use** but still editable), AWS SMS, and inbox reading
(Microsoft Graph, Gmail IMAP). One **Save delivery rates** saves every card. Each card has:

- **Live status**, refreshed every 15 seconds: the rate in use and why ("Now: 12.6 recipients/sec · Smart · 90% of
  the 14 recipients/sec limit (reported by AWS 3 min ago)"), or "Paused until …" / "Stopped: …" while the provider
  has asked to wait or refused; the provider limit and where it comes from; and each rolling 24-hour (Graph: also
  hourly) limit with what has been used and where campaigns stop.
- **Smart rate** (on by default): adjusts the rate to actual conditions. It uses the limit the provider reports
  (SES, AWS SMS) or documents, slows down when the provider throttles, then speeds up step by step, never above
  the provider limit. While it is on it takes priority over the manual rate.
- **Manual rate**, in the channel's unit: the fixed rate used while Smart rate is off. It is read-only while Smart
  rate is on but always kept, and it cannot be above the provider limit.
- **Advanced: provider limits**: the provider rate limit, SMS message parts per second, the daily (and for Graph,
  hourly) limits, the budget headroom and the share campaigns leave for login codes and tickets. A blank field
  shows what applies instead. A documented limit can be lowered here but not raised above its `DELIVERY_RATES`
  value (raise it with `DELIVERY_RATES_OVERRIDES` when the provider grants more, see
  [Environments](../deployment/environments.md#delivery-rates)). SES and AWS SMS also list what AWS last reported, with
  **Check provider limits now**. **Reset Smart rate** starts Smart rate afresh; **Resume sending** (shown while a
  pause or stop holds the channel) clears it.

Every save and button writes an admin history line such as `sms_send: Smart rate on→off; manual 1→0.5`.
Notification Delivery, the Delivery Dashboard and the campaign send confirmation show the same status line.

The manual rate is the total for the channel, sign-in codes and tickets included, and campaigns get at most 80 % of
it; the old campaign send rate paced only queued mail. The SES card's **Provider rate limit** starts at that old
campaign send rate, marked as carried over: it applies only until AWS reports the account's limit, which then
replaces it (enter another value to make it your own limit). **Internal domain** (Gmail API, Advanced) accepts only
the domain of an account on the Gmail API allow-list or a parent domain of it, since recipients there do not count
against Google's external limit.
How the rate, the daily limits and the stops are worked out, every seed with its source, and what to do when a
provider stops sending: [Delivery rates](../integrations/delivery-rates.md).

### Login link tokens

`LoginLinkToken` (`src/apps/mail/models/login_link.py`) is the single mechanism behind emailed one-click login links — both campaign `{{login_link}}` links and the login button in event ticket confirmation emails. Clicking a link authenticates the user via `POST /mail/login-link/` (legacy alias: `/mail/magic-login/`) and redirects to the configured destination (campaign `login_redirect_path`, or the per-token path — `/event-registration?event=<event-slug>` for ticket links).

Policy is configured at the issuing source and enforced per token:

- **Validity** — `EmailCampaign.login_link_validity_days` (default 7) / `Event.ticket_login_validity_days` (default 30), 1–90 days, frozen onto each token at send time.
- **Reuse** — `EmailCampaign.login_link_reusable` (default off) / `Event.ticket_login_reusable` (default on). Read live at login time, so unticking the flag immediately blocks further reuse of already-used links — a kill switch.
- **Revocation** — admin actions on Broadcast Email (campaign), Event Registrations, and the read-only **Login Links** changelist (`/admin/mail/loginlinktoken/`) expire tokens immediately. The raw token value is never displayed in admin.

Resending a ticket email revokes the registration's previous link before issuing a new one.

### Gmail import

The campaign admin includes a Gmail import feature (`src/apps/mail/services/gmail_import/`) that can fetch email templates from a Gmail account for use as campaign bodies.

### Recipient logs

`RecipientLog` (`src/apps/mail/models/recipient_log.py`) tracks per-recipient delivery:

| Field | Purpose |
|-------|---------|
| `campaign` | FK to EmailCampaign |
| `email` | Recipient email address |
| `status` | Delivery status: pending, processing, retry scheduled, paused by delivery limits, sent, delivered, bounced, complained, rejected, failed, uncertain delivery |
| `sent_at` | Timestamp |
| `error` | Error message if failed |

Viewable as inline records in the campaign admin.

## Related pages

- [Django Admin](django-admin.md) — Admin interface and customization
- [API: Auth & Mail](../api/auth-and-mail.md) — Auth and mail API endpoints
- [Architecture: Integrations](../architecture/integrations.md) — AWS SES, SMTP, Microsoft Graph, the Gmail API, and AWS SMS configuration
- [Microsoft Graph email](../integrations/microsoft-graph-email.md) — Entra app setup, mailbox scoping, limits, and errors for the Graph email provider
- [Gmail API email](../integrations/gmail-api-email.md) — service account, domain-wide delegation, key install, the access check and Sent copies for the Gmail API provider
- [Delivery rates](../integrations/delivery-rates.md) — Smart rate, manual rate, budgets, stops and Resume for every delivery channel
- [Operations](operations.md) — Operational tasks

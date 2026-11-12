# Member & Mail Tools

Member management, email campaigns, and contact administration.

## Member management

### Member model

`Member` (`src/apps/authn/models/members/member.py`) extends Django's `AbstractUser` with `ProjectControlModel` (UUID PK). Key fields:

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Primary key (not auto-increment); `USERNAME_FIELD`, there is no username |
| `email` | EmailField | Unused: inherited from `AbstractUser` and left blank. Sign-in uses the verified contact emails (below) |
| `is_active` | BooleanField | **Account active** in the admin: the account can sign in, and is in the All subscribers / All active members / Staff audiences. Independent of the contact flags |
| `registration_pending` | BooleanField | **Unfinished sign-up** (read-only): a self-service registration not yet completed |
| `first_name`, `last_name` | CharField | Required |
| `middle_name` | CharField | Optional |
| `organization` | CharField | Optional |
| `profile_image` | ImageField | Profile photo |

There is no member-level subscription field: newsletter subscription is the `subscribe` flag of each contact email
(below). The profile API's `email_subscribe` is the primary contact email's flag.

### Admin capabilities

In Django admin → Members & Auth → Members:
- Search by email address (the exact address first, then addresses starting with it), name, organization, title or
  Member UUID; a phone number typed on its own (any format, at least 3 digits) searches phone numbers. Member pickers
  on other pages search the same way. See [Member and contact admin search](django-admin.md#member-and-contact-admin-search)
- Filters (`src/apps/authn/admin/members/filters.py`): **Account active** (yes / no / unfinished sign-up), **Primary
  email** (verified / unverified / none), **Unverified emails**, **Newsletter (All subscribers)** (subscribed at the
  primary / at another address only / nowhere), **Phone** (verified / unverified only / none), staff status, date
  joined. Contact Emails: **Verified (sign-in)** (incl. unverified emails and unverified primaries), **Subscribed
  (newsletters)**, email type, **Member account** (active / inactive / staff or I2G Master / unlinked), with an
  **Account active** column; Contact Phones: **Member account** too
- **Switch primary email** on the member page (and **Make primary…** on each verified Contact Emails row): see
  [Switching the primary email](#switching-the-primary-email)
- Inline contact emails and phones
- Import/export members via Excel (openpyxl)

Admin access is per Django app: staff granted an app in `admin_apps` have full control of that app's records and
configuration, like a superuser (who has every app). Only the Member privilege fields stay with superusers:
`is_staff` and `admin_apps` are edited by superusers only, and superuser status is not editable in the admin at all.

### Contact information

Members can have multiple contact emails and phones:

- **ContactEmail**: Types (primary, secondary, other), verified flag, and a per-address `subscribe` flag (on by
  default). That flag is the only thing that decides whether the address receives newsletters (see
  [Audience types](#audience-types)); `verified` plays no part in it
- **ContactPhone**: Region support, verified flag, subscribe flag

Contact verification uses the email challenge system or AWS SNS SMS.

### Account active, Verified and Subscribed

Three independent flags; none changes another, and none is changed by a bounce report:

| Flag | Belongs to | Read by | Not read by |
|---|---|---|---|
| **Account active** (`Member.is_active`) | The account | Every sign-in path; the All subscribers, All active members and Staff audiences (email), All members and Staff (SMS) | Selected Members, Manual Emails and event audiences, which include inactive members (the SMS Subscribers audience does too: unchanged, a known inconsistency) |
| **Verified** (`ContactEmail.verified`, `ContactPhone.verified`) | One address / number | Sign-in (email code and password with any verified address; admin codes with a staff member's verified primary; SMS sign-in with a verified number); only a verified address can become primary; the recovery-contact count | No email audience |
| **Subscribed** (`ContactEmail.subscribe`) | One address | The All subscribers audience only ("primary only" uses the primary's flag) | All active members, Staff, Selected Members and event audiences; transactional mail |

To stop campaign mail to one bad address, use Email Monitoring → Bounced addresses → **Mark undeliverable** (every
campaign audience skips it, at resolution and at send time). Unticking Verified stops sign-in only; deactivating the
account stops sign-in and the member audiences for every address.

The admin labels and help text say this on every Members form (`src/apps/authn/admin/members/help_texts.py`). They
are set through the forms' `Meta.labels` / `Meta.help_texts`, which Django also applies to read-only fields, so the
models (and their migrations) are unchanged. Unticking a member's last verified email or phone, deleting it, or
moving it to another member is allowed but warned about (`sign_in_warning.py`): after the save or delete, and for an
edit (including removing the row on the member page) already on the type-to-confirm page; the delete confirmation of
the Contact Emails / Contact Phones admin shows no warning row. The member then cannot sign in with a code or a
password until one is verified again; only a personal sign-in link from an email (`LoginLinkToken`, which checks an
active account and expiry only) still works. The member API still refuses to delete that last contact.

### Switching the primary email

`MemberAdmin`'s **Switch primary email** (an Unfold detail action, `/admin/authn/member/<id>/switch-primary/`) and the
**Make primary…** link on each verified Contact Emails row open the same page. A GET changes nothing: it lists the
member's addresses with their type before and after, and spells out what the switch changes for signing in and for
campaigns. The POST (CSRF, the typed word `switch` while `ADMIN_REQUIRE_CONFIRMATION` is on) calls
`apps.authn.services.contacts.primary_switch.switch_primary_email`, which:

- locks the member row and refuses (`StaleSwitch`) when the member or their addresses differ from the page's
  fingerprint, so a stale page never switches;
- refuses an address that is not the member's or not verified, with what to do instead;
- calls the existing `make_contact_email_primary` in the same transaction (old primary → `secondary`, old secondary
  → `other`), then reads back every changed type.

`log_switch` writes a History line on the member ("Primary email switched from … to …") and one on each changed
address, inside the switch's transaction (`switch_primary_email(..., actor=..., via=...)`), so a switch is never
committed without its History; the application log gets ids only. The Contact Emails action **Make selected email primary** uses the same
service and history. Subscriptions, verification and sessions never change, and nothing is sent; the page warns when
the switch changes who receives "primary only" campaigns. Permission: the `authn` app plus `user_can_manage_member`
(on a staff or superuser account, the I2G Master or the account holder); the button and links are hidden from
anyone else, and the view re-checks both.

### Phone numbers and SMS sign-in

Only a **verified** phone number can be used to sign in with a texted code (passwordless sign-in, password sign-in
by phone, password reset by phone). A number saved on an account but never verified, for example one added by staff
or a member import, is refused without saying so: the sign-in page answers as if a code had been sent, and no text is
sent. The member verifies the number with a one-time code from **Account → Phone Numbers → Verify**; from then on it
signs in.

A number becomes verified only with a code; there is no tick for it:

- The **SMS sign-in** column of Contact Phones and the member page's phone rows show **Verified · SMS sign-in on** or
  **Unverified · no SMS sign-in**; the member list adds `(unverified)` to an unverified primary phone.
- The **Verified** box can be unticked (or use **Mark selected phones as unverified**) to stop SMS sign-in, but not
  ticked: a phone added in the admin starts unverified, and changing a number's digits makes it unverified again
  (writing the same number differently does not).
- **Verify by SMS code** (the link next to an unverified number) is the staff path for a member who cannot sign in
  another way, for example a phone-only member whose only number is unverified: talk to the member (in person, or on a
  call to them at a contact you already trust), **Send code**, ask them to read it to you, and enter it. The code goes
  to that number only, is valid for 10 minutes, allows 5 tries and follows the same per-number limits as every code.
  Both steps are written to the admin history. A member who can sign in with their email should verify the number
  themselves on their account page instead.
- Staff with the Members app may do this for regular members; a staff or superuser account's number needs an I2G
  Master.

### Admin invitations

`AdminInvitation` allows existing staff to invite new admin users:
1. Staff creates an invitation with the invitee's email
2. System sends an invitation email with a token
3. Invitee follows the link to set up their admin account

## Email campaigns

### Overview

The mail app (`src/apps/mail/`) provides email campaign functionality through Django admin. Campaigns are composed in the admin using CKEditor 5 and sent to selected audiences.

### Choose the email sender

**Broadcast Delivery → Email Sending Method** in the sidebar (`/admin/mail/sending-method/`) sets
which API sends all site email. It names the method in use and has one card for each of **AWS SES**,
**SMTP**, **Microsoft Graph** and **Gmail API**. Notification Delivery shows the method in use with a link
here, and the campaign send confirmation links here too. Each card says whether that method is **In use**, **Ready**
or **Not ready** (and why: the same check that switching to it runs, so Microsoft Graph and the Gmail API need
their go-live checks), and has:

- **Send test**: a test email through that method, to an address you enter, without switching to it. The test
  page's **Send through** row moves between methods; one that is not ready cannot be sent through.
- **Use for email**: switch all site email to that method (Mail app staff; the change is in the admin history).
  Microsoft Graph can send only from a mailbox in its scope: when the From email is outside it but the Graph
  **Sender Mailbox** is an address in it, the card says so and the switch also changes the From email to that
  mailbox (switching back later keeps it; change it on Edit Notification Delivery).
- **Configure**: where that method is set up, when you have the access it needs (SES on Edit Notification
  Delivery; SMTP on its Service Credentials tab, or Edit Notification Delivery without the Core app; Microsoft
  Graph and the Gmail API with the Core app).

**Edit Notification Delivery** sets the sender name and email address and the active configuration. Under
**Email Sender**, **Provider** is the same switch as **Use for email**.

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
  Graph can be selected. In production Graph can be selected only after an
  admin with the Core app has run the access check with the current certificate and it
  matched the approval (the panel's **Go-live evidence** line says what is
  missing; see [Validate the access restriction](../integrations/microsoft-graph-email.md#validate-the-access-restriction)).
  Graph authenticates with a certificate only; an
  admin with the Core app installs it there, and its private key is kept in the credential
  store, never in the database. The sender mailbox
  defaults to the From email; both must be in the scope with send permission.
  With read permission, **Mail → Inbox** reads that mailbox through Graph
  instead of the Gmail import account; its **Sent** folder (and any message
  from the site's own address) is then shown to staff with the Mail app only, and Sent
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
  and the list are managed on the configuration's own page (Core app). The
  From email must be on the list, and email can switch to the Gmail API (or
  change its From address there) only after the access check passed for the
  installed key. Gmail keeps a copy of everything it sends in the account's Sent
  folder: mail with sign-in codes or login links is tagged and never shown from
  that folder by **Mail → Inbox** or **Import from Gmail**, and the inbox's **Sent** folder is
  shown to staff with the Mail app only while the Gmail import account is one the site sends
  as. Rates and daily limits are on **Mail → Delivery Rates**. Setup:
  [Gmail API email](../integrations/gmail-api-email.md).
- AWS settings remain available for SMS even when email uses SMTP, Microsoft
  Graph or the Gmail API. Changing the email provider does not switch the SMS provider.

This selection applies to verification codes, admin invitations, tickets,
campaigns, inbox replies, and the **Send Test Email** action (which tests the method in use; each card's
**Send test** tests its own). Saving settings does not send a message; use a test to check delivery explicitly.

### Campaign model

`EmailCampaign` (`src/apps/mail/models/campaign.py`):

| Field | Purpose |
|-------|---------|
| `subject` | Email subject line |
| `body` | The message. **Email format** on the form is not a model field: *HTML* stores the body behind the `<!-- raw-html -->` marker line (`services/campaign/preview.py`, `HTML_MARKER`) and sends it as written in the CodeMirror editor; *Plain Text* stores it bare and sends it escaped, with line breaks and auto-linked URLs. The form strips the marker for editing, drops any marker pasted into the editor, and stores exactly one on save; the read-only view of a sent campaign names the format and its copy button copies the body without the marker |
| `audience_type` | Target audience selector |
| `member_email_scope` | **Send to**: each member's primary contact email only, or every contact email (member-based audiences) |
| `include_unsubscribe_header` | **Include one-click unsubscribe** (default on): the footer unsubscribe link and the RFC 8058 `List-Unsubscribe` headers |
| `status` | `draft`, `queued`, `sending`, `partial` (Partially sent: some recipients failed or are paused), `sent`, `failed` |
| `total_recipients` | Calculated recipient count |
| `sent_count` | Successfully sent count |

### Audience types

| Type | Recipients |
|------|-----------|
| `subscribers` | **All subscribers (subscribed email addresses only)**: active members, at their subscribed addresses only (below) |
| `event_registrants` | Members registered for a specific event |
| `selected_members` | Manually selected members (ManyToMany) |
| `manual` | Comma-separated email addresses |
| `ticket_type` | Registrants with a specific ticket type |
| `checked_in` | Registrants who checked in to an event |
| `not_checked_in` | Registrants who did not check in |
| `all_members` | **All active members (subscribed or not)**: every active member, including people who unsubscribed, at the primary address (members without one get nothing) or, with **Send to: all emails**, at every saved address |
| `staff` | Staff users only (active members marked as staff, addressed like All active members) |

Audience resolution is handled by `src/apps/mail/services/audience/` (`resolvers.py`). The recipient list is resolved
once, when sending starts (with the background worker, when the campaign is queued), so an address unsubscribed after
that still receives that campaign.

**Suppressed addresses.** Every audience type leaves out an address that staff marked undeliverable or suppressed on
**Email Monitoring → Bounced addresses** ([Email Monitoring](../integrations/email-monitoring.md#bounced-addresses)),
compared in lower case (event audiences compare the attendee email). The previews and the send confirmation show
"N recipients skipped: undeliverable", and a recipient queued before the address was suppressed is checked again just
before sending and recorded as failed ("Not sent: this address is suppressed for bulk mail"). A member whose primary
address is suppressed gets no primary-only campaign until another verified address is made primary. Transactional mail
(sign-in codes, tickets, notifications) is never suppressed. The labels of the two member-wide audiences name their one difference, the
`subscribe` flag, and the **Audience type** help text on the campaign form spells out who each one reaches
(`models/campaign.py`, `AUDIENCE_HELP_TEXT`).

**All subscribers.** The per-address `subscribe` flag is authoritative. Only members with `is_active` set are
included, and each is mailed only at addresses whose own flag is on:

- **Send to: primary only** — the primary address, and only if it is subscribed. A subscribed secondary address
  does not stand in for an unsubscribed primary; such a member gets nothing.
- **Send to: all emails** — every subscribed address (primary, secondary, other).

`verified` is not required. The member import creates a new member's addresses unverified and subscribed unless the
sheet says otherwise, so requiring verification would drop most of the mailing list. An address the import adds to an
existing member always starts unverified, and it is subscribed only if that member is subscribed at another address.
The import never re-subscribes an address unless an admin ticks that re-subscription in the import's review (see
[Member import/export](operations.md#member-importexport)). The
one-click unsubscribe link turns off every address of the member at once (see
[Auth & Mail](../api/auth-and-mail.md#one-click-unsubscribe-and-resubscribe)); members change single addresses on
`/account`. When **Exclude audience** is All subscribers, the same rules build the exclusion list with the
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

**Open product question: the other audiences ignore the flag.** Only All subscribers reads `subscribe`. All
active members, Staff Members and Selected Members mail the primary (or every) address of each member, and the
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
| `{{ login_link }}` | The recipient's login link (see [Login link tokens](#login-link-tokens)); for a manual address that belongs to no active member, a link to the site's sign-in page (`FRONTEND_URL/login`) |

There is no unsubscribe placeholder. With **Include one-click unsubscribe** on, every email to a member (any
audience) gets an "Unsubscribe from newsletters" link in the footer and the RFC 8058 `List-Unsubscribe` /
`List-Unsubscribe-Post` headers, both pointing at the backend page `/mail/unsubscribe/{token}/` (valid 365 days; see
[Auth & Mail](../api/auth-and-mail.md#one-click-unsubscribe-and-resubscribe)). Manual addresses that belong to no
active member get neither, and nothing is added while `BACKEND_URL` is unset. The admin preview shows a placeholder
link.

**Manual Emails and members.** Each typed address is matched, ignoring letter case, to the active member whose
contact email (primary, secondary or other) it is, in one query when the audience is resolved
(`src/apps/mail/services/audience/resolvers.py`, `_manual`). A matched address is treated like a Selected Members
recipient: the name tags, the personal `{{ login_link }}` and the unsubscribe link are that member's, and the message
still goes to the address exactly as typed. An address no active member owns (or that two members hold in different
letter case) gets empty name tags, and its `{{ login_link }}` becomes a link to the sign-in page. That link is not a
credential, so the message keeps its Sent copy. Lines that repeat an address in another letter case are sent once.
When the subject or body uses `{{ login_link }}`, the send confirmation page says how many recipients have no account
and will get the sign-in page instead. Until 2026-11-03 manual addresses were never matched, so `{{ login_link }}`
rendered as nothing for every manual address.

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
in-process sender (no background worker) sends a recipient the provider
throttled again after the cooldown, and marks the remaining recipients
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
the sender mailbox, where bounce processing reads them for
[Email monitoring](../integrations/email-monitoring.md) without changing the recipient log, and its
uncertain outcomes are explained in the
[error reference](../integrations/microsoft-graph-email.md#error-reference). The
Delivery Dashboard under **Delivery Operations** charts SES CloudWatch metrics
only and shows a notice while another provider is active.

### Sent campaigns are locked; duplicate to send again

Once a campaign leaves **Draft** (queued, sending, partially sent, sent or failed) its subject, content, audience
and login-link validity are read-only: the row is the record of what went out, its recipient logs and login links
belong to that send, and its counters are aggregated from those logs. A banner on the change page says so.
**Reusable login links** stays editable because it is read at login time and works as a kill switch for links
already sent. The **Send Campaign** and **Import Gmail HTML** actions are not offered on a locked campaign.

To send the email again, to send a changed version, or to send it to more people, use **Duplicate campaign** (a
detail action; **Duplicate as new draft** does the same from the list). It asks for a name and an audience, then
creates a new draft with the same subject, content and settings and either the same audience or an empty **Manual
Emails** list for further addresses, and opens it. The suggested name is numbered the way a file system numbers
copies: the original's name with the lowest number no campaign uses, `Spring invitation (1)`, then `(2)`; any
leading `Copy of` (the former naming, in any letter case) and a trailing `(N)` come off first, so a copy of
`Copy of Spring invitation (2)` is `Spring invitation (3)` when `(1)` and `(2)` exist. Names are compared ignoring
letter case. Nothing is sent until that draft is previewed and sent.
Additional recipients are a new campaign on purpose: every send issues its own login links and recipient logs, and
one campaign cannot send to the same address twice. Addresses that already received the original are not excluded
automatically; list only the new addresses, or add an **Exclude audience** when the new list overlaps a member
group (`services/campaign/duplicate.py`).

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

## Broadcast SMS: opt-outs, quiet hours, links and ticket texts

What staff need to know before texting people (full detail: [AWS SMS](../integrations/aws-sms.md)):

- **SMS Opt-outs** (Broadcast Campaigns tabs) lists every number no text goes to: people who replied STOP (read
  from AWS every hour, or **Sync with AWS now**) and numbers staff added because someone asked them to stop. A
  Broadcast SMS skips them ("N recipients skipped: opted out of texts"), sign-in codes are refused for them, and
  the SMS Log shows **Opted out** instead of "Failed". Opting out unsubscribes the member's phone; replying START
  later never subscribes it again. Only staff opt-outs can be lifted here.
- **Quiet hours** (SMS Settings, 20:00–09:00 Pacific by default): a Broadcast SMS started then is queued until
  they end (with background jobs off it cannot be sent until then). Sign-in codes are never held.
- **Footer**: "Reply STOP to opt out." is added to each Broadcast SMS that does not already tell people how to opt
  out (such as "Reply STOP"; a plain "Stop by our booth" still gets the footer).
- **Cost**: the message field shows the encoding, the segments and the estimated cost as you type; the send
  preview and the confirmation show the total for the real recipients. Avoid emoji and curly quotes: one of them
  more than doubles the number of segments.
- **Links** (`{{login_link}}`, `{{ticket_link}}`, `{{event_link}}`) and **ticket texts for phone-only
  registrants** are **off** until the sending number's 10DLC or toll-free registration is confirmed to allow
  embedded links. While they are off, a message with a link placeholder cannot be saved or sent. One-tap
  **personal sign-in links** are a separate switch that only the I2G Master can turn on; even then a link signs a
  member in only when it is texted to that member's own verified phone. Turning personal sign-in links (or links in
  SMS) **off revokes every personal link already texted, for good**: turning it back on does not bring them back,
  and whoever opens one lands on the normal sign-in page. SMS Settings says how many would be revoked before you
  save, and **SMS link revocations** records who turned them off, when, and how many links it revoked.
- **Short /register link**: SMS Settings shows the QR code for `/register` (SVG and PNG) and where it leads (by
  default the sign-in page, which takes an email address or a phone number).

## Related pages

- [Django Admin](django-admin.md) — Admin interface and customization
- [API: Auth & Mail](../api/auth-and-mail.md) — Auth and mail API endpoints
- [Architecture: Integrations](../architecture/integrations.md) — AWS SES, SMTP, Microsoft Graph, the Gmail API, and AWS SMS configuration
- [Microsoft Graph email](../integrations/microsoft-graph-email.md) — Entra app setup, mailbox scoping, limits, and errors for the Graph email provider
- [Gmail API email](../integrations/gmail-api-email.md) — service account, domain-wide delegation, key install, the access check and Sent copies for the Gmail API provider
- [Delivery rates](../integrations/delivery-rates.md) — Smart rate, manual rate, budgets, stops and Resume for every delivery channel
- [AWS SMS](../integrations/aws-sms.md) — SMS opt-outs and their AWS sync, the footer, quiet hours, the cost estimate, links in SMS, ticket texts and the /register QR code
- [Operations](operations.md) — Operational tasks

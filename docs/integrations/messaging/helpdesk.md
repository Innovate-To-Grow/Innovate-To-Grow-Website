# Helpdesk (tickets from the i2g@ mailbox), a ServiceNow-style service desk

Every message that reaches the Inbox of the site's Microsoft Graph mailbox (`i2g@ucmerced.edu`) becomes a
ticket in the Django admin (**Helpdesk** section), or joins the ticket of its conversation. Automated mail
(out-of-office replies, left-the-organisation notices, bounce reports, read receipts, list mail and newsletters,
spam, the site's own mail) also becomes a ticket, but one that is closed at once, hidden from the default queue,
never notifies anyone and never reopens. A person's answer to the site's own mail stays a person's, even when it
was sent from a CRM or marketing tool.

Tickets are worked the way ServiceNow works incidents ([Working tickets](#working-tickets-servicenow-style)):
impact × urgency gives the priority, a ticket has an **assignment group** and an **assignee**, an **SLA** clock
gives its first-response and resolution due times, and resolving it records a **resolution code** and notes.
Resolved tickets close by themselves after 7 days.

The helpdesk still starts in **shadow mode**: it reads the mailbox and writes tickets, and **sends nothing**. Shadow
mode is a switch in Helpdesk → Settings. Off, staff **reply to the requester from the ticket page** (ServiceNow's
"additional comments"; internal notes stay the "work notes"), and the **acknowledgement** of a new ticket and the
**assignment notifications** are sent when their own switches are on ([Replies and notifications](#replies-and-notifications)).
Either way nothing in Outlook changes (no mail is marked read, moved, flagged or forwarded). The design and the open
questions are in the Item 2 plan (`item2-helpdesk-bounces-plan-2026-11-10.md`, §2, kept with the project notes, not in
this repository), which predates the decisions recorded here: automated mail *is* a ticket (closed and hidden), and
the H2 phase is built as described below (replies, acknowledgement, notifications, SLA, response templates).

## For staff

| Sidebar entry | What it shows |
|---|---|
| **Queue** | People's open tickets (new, open, pending), most recent activity first. A dot marks an unread customer message. |
| **My Tickets** / **My Groups** / **Unassigned** | The same list, assigned to you / to an assignment group you are a member of / to nobody. |
| **SLA Breached** | Tickets whose first response or resolution is overdue (flagged, or past due and not flagged yet). |
| **Automated & Spam** | Automated mail and spam (all statuses). Use **Not automated: move to the queue** when a person's message landed here. A reply to the site's mail that came through a mailing list is list mail here, flagged **reply to our mail**: read it, and move it to the queue if a person wrote it. There is no merge here: nothing is merged into automated mail or spam. |
| **Ingest Problems** | Messages that could not be imported (after the last attempt) or were gone from the mailbox, with **Retry**. |
| **Categories**, **Assignment Groups**, **SLA Targets**, **Response Templates** | Ticket categories (each may name a default group); the teams that work tickets; the response and resolution targets per priority; canned replies. |
| **Settings** | The helpdesk's limits, retention periods and switches (shadow mode, acknowledgement, notifications, auto-close), under the **intake card** (how the helpdesk reads the Inbox: [Intake controls](#intake-controls)). |

The list filters (**Mail**: people / automated & spam / everything; **Status**; **Assignee**; **Assignment group**:
my groups / no group / one group; **SLA**: breached / due within 24 hours / no SLA; **Unread**; priority; category)
and the search (a number such as `1234` or `I2G-#1234`, the subject, or the requester's address or name) narrow the
queue. The **SLA** column shows the clock that matters now: the first response until it is met, then the resolution
(on track with its due time, at risk, paused, breached or met).

**The ticket page** edits status, impact and urgency (the priority follows, read-only), category, assignment group
and assignee, and the resolution code and notes (no typed confirmation; every change is in the ticket's timeline and
the admin history). It shows the two SLA clocks, the timeline (messages, replies with their delivery state, internal
notes, field changes), the **reply form** (only while shadow mode is off) and the internal-note form. A merged
ticket's status cannot be changed, and **Merged** is not in the Status list: only a merge makes a ticket merged.
Notes are seen only by staff with the Helpdesk app and are never sent. Opening a ticket marks it read.

- Message HTML was sanitized when it was imported and is shown in a sandboxed frame without scripts; images are
  replaced by `[image]` (remote images would track the reader; inline ones are listed as attachments).
- A message the scam checks found suspicious carries a warning; do not open its links before checking the sender.
- Personal sign-in and subscription links quoted in a message are shown as `[sign-in link removed]`.
- Attachments download as files. Archives (zip, 7z, rar, …) open a warning first; blocked file types
  (executables, scripts, disk images, HTML/SVG, macro-enabled Office files, OneNote, CHM) and files over the size
  limit keep only their name, size and type: open the message in Outlook if you need them.
- Automated messages in a thread are collapsed.

**Bulk actions:** assign to me, unassign, close, reopen (never an automated ticket), mark as read, move to the
queue, and, behind a typed confirmation (`MERGE`, `SPAM`), **merge** and **mark as spam**. None of them changes a
merged ticket's status (a merge is final: its messages are on the ticket it was merged into, and so is its mail).

**Merging** puts every selected ticket into the oldest one; nothing is deleted. It never goes into automated mail or
spam (a person's messages would be hidden there), and spam is never merged: when the oldest selected ticket is
automated mail or spam, or another selected ticket is spam, nothing is merged and the reason is shown before the
confirmation is asked for. The rule is the helpdesk service's (`services/tickets/merging.py`), so it holds when the merge
runs too, and `Ticket.clean()` refuses such a merge target for any form. Automated mail merged into a person's ticket
shows there collapsed and changes nothing else on it (not its status, unread mark, participants or last activity),
as when it threads there by itself; the merged ticket stays hidden (still automated, now merged), and later mail of
its thread lands on the person's ticket.

## Working tickets (ServiceNow style)

| ServiceNow | Helpdesk | Notes |
|---|---|---|
| Number `INC0010001` | `I2G-#1234` | Also the subject token that threads mail back to the ticket. |
| State | Status: New, In progress, On hold – awaiting requester, On hold – awaiting internal, Resolved, Closed (and Merged, Spam) | A requester's reply puts "awaiting requester" back to In progress and reopens a ticket closed less than `reopen_window_days` ago. |
| Impact × Urgency → Priority | Impact 1–3 × Urgency 1–3 → 1 Critical, 2 High, 3 Moderate, 4 Low (`services/tickets/priority.py`) | ServiceNow's "5 – Planning" (3 × 3) is Low. A person's new ticket starts at 2 × 2 (Moderate), automated mail at 3 × 3 (Low). The stored values (`urgent`, `high`, `normal`, `low`) are unchanged. |
| Assignment group / Assigned to | **Assignment Groups** (members, manager) and the assignee | A category's **default group** is set on a ticket given that category while it has no group (assignment rule). With a group that has members, the assignee must be one of them. |
| Work notes / Additional comments | Internal notes / replies to the requester | Replies only while shadow mode is off. |
| SLA definitions | **SLA Targets**, one per priority | See [SLA](#sla). |
| Close code / close notes | Resolution code / resolution notes | A code is required to resolve or close a ticket on the ticket page (the bulk Close action does not ask). |
| Auto-close of resolved incidents | `auto_close_resolved_days` (7) | Closed by the worker's hourly maintenance ("Helpdesk SLA and auto-close"); a reply before then reopens. |
| Templates | **Response Templates** | Choose one above the reply form and press **Insert**: `{ticket}`, `{requester_name}`, `{subject}`, `{agent_name}` are filled in, then edit and send. Templates of the ticket's category are listed first. |

### SLA

Each priority's **SLA target** (Helpdesk → SLA Targets) gives a first-response time and a resolution time, in
calendar time (no business hours). Seeded by `helpdesk.0004`: Critical 1 h / 8 h, High 4 h / 2 days, Moderate 1 day /
5 days, Low 3 days / 10 days. A target switched off means no SLA for that priority; targets cannot be deleted.

- The clock starts when the ticket's first message arrived. Automated mail, backfilled mail (imported more than
  `backfill_age_hours` late) and tickets from before this release have no clock.
- **First response** is met by the first reply sent from the ticket, or by staff moving the ticket out of New (the site
  cannot see answers written in Outlook; moving the ticket on stands for them). The acknowledgement does not count.
- **Resolution** runs while the ticket is New, In progress or On hold – awaiting internal, and stands still while it
  is On hold – awaiting requester, Resolved or Closed. When it runs again (the requester replied, the ticket was
  reopened) the time it stood still is added to its due time.
- A priority change sets the new priority's targets, from the same start, and judges both clocks again.
- A clock is **at risk** once `sla_warning_percent` (75 %) of its time is used and **breached** once its due time
  passes before it is met. Breaches are flagged when they are seen (a change on the ticket, the worker's hourly
  maintenance, which also writes "SLA breached" on the timeline); the queue's SLA column and filter also show
  overdue clocks not flagged yet. No email is sent for a breach.

### Replies and notifications

Everything here needs **shadow mode off** (Helpdesk → Settings; every change of it is in the admin history and the log
line `helpdesk_shadow_mode`). Sending code lives only in `services/outbound/`; a test pins that no other helpdesk
module imports a sending API, and that each job checks shadow mode before it sends.

- **Replies.** The reply form on the ticket page sends to the requester (optional Cc, at most 10; Cc addresses
  become participants, so their answers thread too) from the site's address, subject `Re: <subject> [I2G-#1234]`,
  with the Mail app's branded reply layout, the requester's latest message quoted, and a footer asking to keep the
  number in the subject. The status can be set with it (default: On hold – awaiting requester). Microsoft Graph cannot
  send `In-Reply-To`/`References`, so the subject token is what threads the answer back (accepted only from a
  participant, as before). The reply is stored on the ticket and sent by the background job `helpdesk.send_reply`
  (transactional lane, paced by the delivery-rate limiter); the timeline shows it Queued, then Sent, or Failed with
  the reason (a fixed text; the provider's error stays in the job and the server log). A job is never retried once the
  provider call began, so a reply is never sent twice; when it is uncertain whether it went out, the timeline says so.
- **Acknowledgement** (`send_acknowledgement`, off by default). When a person's message opens a new ticket, the
  requester gets `acknowledgement_text` with the ticket number. Never for automated mail, spam, backfilled mail or a
  message that must not be answered automatically (`shadow.automatic_reply_allowed`, RFC 3834), and at most once a
  day per address, so two auto-responders cannot answer each other.
- **Assignment notifications** (`notify_assignment`, on). Assigning a ticket to someone else emails them; assigning it
  to a group with nobody assigned emails the group's members. Never to the member who made the change, only to active
  staff with the Helpdesk app. The email names the ticket (number, subject, requester, priority) and links to the
  ticket page (`BACKEND_URL`); it never contains the requester's message.
- Switching shadow mode back on stops every helpdesk email not sent yet: each job checks it again when it runs (a
  reply then shows as Failed: "shadow mode was switched on").

## How a message becomes a ticket

1. **Intake** (`apps/helpdesk/services/intake/`). The helpdesk's own scan of the Inbox (job
   `helpdesk.intake_scan`, every `inbox_scan_interval_seconds`, 2 minutes; 30 s while catching up) lists it
   incrementally from the helpdesk's own checkpoint (less a 15-minute overlap; the first scan looks back 72 hours)
   and records every listed message once in `core.InboundMessage` (mailbox, Graph id, internet Message-ID,
   conversation id, received time, sender, scrubbed subject; never a body). It opens no message, lists with the
   bounce scan's bounds and the same `graph_read` pacing, and a scan that recorded new mail queues the job
   `helpdesk.ingest_inbound`. It is separate from bounce processing ([Email monitoring](email-monitoring.md)),
   which reads the same Inbox for reports on its own schedule and checkpoint: pausing or rescanning one never
   moves the other. Polling only: no webhooks.
2. **Import** (`apps/helpdesk/services/ingest/`). The job takes due rows, oldest first, within a budget (100
   messages or 60 s per run), and for each: skips it as a duplicate when a ticket already holds its Message-ID;
   reads its raw MIME through the site's Graph reader (GET only, paced on the `graph_read` channel, at most
   25 MB); parses it under the same hardening as bounce reports; classifies it; threads and stores it. A message
   gone from the mailbox is skipped with the reason; a failure is retried with backoff and, after 5 attempts,
   listed under Ingest Problems (so is a message the worker stopped on at every attempt, once it is found left
   half-done). A throttle from Microsoft ends the run and the message waits as long as asked.
   While a campaign is sending, the job waits (`pause_while_campaign_sending`): reads and sends share Outlook's
   per-mailbox limits. While the intake is paused, the import waits too.
3. **Classification** (`apps/core/services/email/inbound/classification/classify.py`, pure): the site's own message (from its
   address *and* proven by DKIM or Exchange's internal marker), bounce or delay report, read or delivery receipt,
   automatic reply (vacation, left the organisation, other), other system mail (calendar replies, quarantine
   notices, auto-generated notices), list or bulk mail, spam (Exchange SCL ≥ 5 or its spam verdict), else human.
   Only strong signals (headers, and the auto-reply subject prefixes mail systems write in several languages)
   make a message automated; **anything uncertain is human**. Content-only signs become hints (flags such as
   `possible_auto_reply`). A human message is also scored by the Mail app's rule-based scam checks (never the
   optional Bedrock review): high → spam, medium → a "suspicious" flag. A message that claims the site's address
   without proof is flagged suspicious. In more detail:
   - **Replies to the site's mail** (`ingest/routing/replies.py`, before classifying): a message whose In-Reply-To or
     References name an email the site sent (the telemetry's `OutboundEmail`, kept 180 days), or, for an email sent
     without a Message-ID the site knows (Graph JSON: campaign mail carrying a sign-in link), a reply from the address
     it went to with the same subject once "RE:", "Automatic reply:" and gateway tags such as "[EXTERNAL]" come off,
     sent at most `reply_match_window_days` (30) before. A message whose In-Reply-To or References name a message of
     a **person's ticket** (not automated mail or spam) counts too: a follow-up in the conversation, most often to an
     answer staff wrote from the mailbox in Outlook, which the site never records (it names no email the site sent,
     so it is attributed to no address). Such a reply is never list or bulk mail on **weak** signals alone: `List-Unsubscribe` and the other unsubscribe headers, an email service provider's or CRM's own headers
     (SendGrid, Mailchimp, HubSpot, Salesforce `X-SFDC-*`, …), `Precedence: bulk`, a no-reply sender, or Exchange's
     bulk complaint level. Those become hints on it (`bulk_headers_on_reply`), so a person who answers a campaign
     from a CRM tool lands in the queue. A list's **distribution** (`List-Id`, `List-Post`, `Precedence: list`) still
     makes it list mail, flagged `reply to our mail` (decision to confirm), and the spam checks always apply. Every
     verdict on a reply carries the hint `replies_to_site_mail`, and a reply to a campaign email opens a ticket
     linked to that campaign either way.
   - **Bulk complaint level.** Exchange's BCL (`X-Microsoft-Antispam: BCL:n`) at or above `bulk_bcl_threshold` (7,
     Exchange Online's own default) makes a message list or bulk mail (a weak signal); it is shown with the
     authentication results.
   - **Automatic replies** (`autoreply.py`): `Auto-Submitted` (not `no`), `X-Autoreply`, `X-Autorespond` and the
     other responder headers, `Precedence: auto_reply`, and the automatic-reply subject prefixes in about twenty
     languages. Exchange's rule markers (`X-MS-Exchange-Inbox-Rules-Loop`, `X-MS-Exchange-Generated-Message-Source`)
     make a message an automatic reply only with a notice's wording, since a rule may also redirect a person's
     message. What the reply says chooses its subtype, read only above the quoted original (Outlook's header block,
     also as an HTML-only message's text gives it, "On … wrote:", `>` lines, an original-message banner), so the
     site's own campaign text, quoted back, never decides: an **absence** (out of office, vacation, leave, "until
     Monday", in English, Spanish, French, German, Portuguese, Italian and Dutch) makes it a vacation reply, and only
     otherwise does wording that the person **left** (no longer with, has left, retired, mailbox closed, "ya no
     trabaja", "ne fait plus partie", "nicht mehr im Unternehmen", …) make it a left-the-organisation notice. A notice
     that says someone left but also mentions a closure, travel or a return (holidays, a break, weekends, "until the
     20th", "upon my return", …) is a vacation reply too, and wording that says only that **nobody reads the
     mailbox** ("this inbox is not monitored") is no notice at all: holiday, weekend and shared mailboxes say so too.
     A lunch break is a temporary absence. A routine office-hours footer (“our office is closed on weekends”)
     or a weekend greeting can accompany a departure notice without hiding its contact details. A notice's **named contact hints**—an address (a new address or someone to
     contact instead, by the words before it), a narrowly introduced name, and a US ten-digit / `+1` phone normalized
     to E.164 `+1`—are kept for manual review, never verified. International phone numbers are ignored; the sender's,
     the site's, no-reply and report addresses and the address the site mailed are never used as the named address.
   - **Loop protection.** Replying to the site's mail never turns an automatic reply into a person's message, so an
     automatic reply to an automatic reply stays automated (it joins its thread and changes nothing). A person's
     message that must not be answered automatically carries the hint `no_auto_response`: RFC 3834's markers (it
     came through a list or a bulk sender, asks for no automatic reply, or has no return path), and also a message
     whose own text looks automated (an absence, a left-the-organisation notice, a system acknowledgement, a receipt)
     or that claims the site's address without proof, since a responder that marks nothing would answer an
     acknowledgement with another. `shadow.automatic_reply_allowed` is the gate the acknowledgement passes
     ([Replies and notifications](#replies-and-notifications)): false in shadow mode, for automated mail, for a message on a ticket that is automated or
     spam, and for such messages.
4. **Threading** (`matching.py`), first match wins: `In-Reply-To`/`References` naming a message of a ticket (a
   reply to a campaign email instead opens a ticket linked to the campaign); the subject token `[I2G-#1234]`
   (also without brackets) **only if the sender is a participant** of that ticket (anyone can type a number); the
   Graph `conversationId`, again only for a participant. Merged tickets are followed.
5. **Rules** (`store.py`):
   - Automated mail joins the ticket it threads to as a collapsed entry and changes nothing on it. Otherwise it
     opens a ticket closed at once (spam: status Spam), low priority, hidden. It never reopens a ticket.
   - A person's message joins its ticket unless that ticket is automated or spam (then it opens a new ticket
     linked to it). A ticket closed less than `reopen_window_days` (14) ago reopens; an older one gets a linked
     follow-up ticket. "Pending customer" becomes "Open".
   - More than `flood_threshold` (10) new tickets from one sender within `flood_window_minutes` (60) are grouped
     into the latest one still open, flagged `flood`; with none open, the message opens a ticket of its own (it is
     never hidden in a closed one).
   - The same message arriving twice (same Message-ID, or the same sender, date, subject and text without one)
     is stored once.
   - The site's own mail keeps no body or attachment (it may hold sign-in codes).
   - Mail imported more than `backfill_age_hours` (24) after it arrived opens tickets marked as backfilled.

**Ticket numbers** come from the PostgreSQL sequence `helpdesk_ticket_number_seq` (created by `helpdesk/0001`,
never below 1001): unique under concurrent creation; a rolled-back number is skipped. SQLite (local development)
takes the highest number plus one. Display: `I2G-#1234`.

## What is stored, and for how long

| Data | Where | Kept (Settings) |
|---|---|---|
| Listed-message metadata | `core.InboundMessage` | `inbound_retention_days` (90) after processing, or after recording while it waits (`EMAIL_MONITORING`) |
| Unverified contact hints copied from a left-the-organisation notice (name, email and US-only `+1` phone) | `mail.BouncedAddress` | Available for review for `left_org_hint_retention_days` (90) after processing. Expired details are hidden immediately and cleared by the next address-counting run. Deleting the source row clears the copy immediately. |
| Message text (personal sign-in links and token-shaped runs scrubbed) and sanitized HTML, capped at 256 KB / 1 MB | `helpdesk.TicketMessage` | 730 days after the ticket closed |
| Attachments (10 MB per file, 25 MB per message; blocked types never) | `helpdesk.TicketAttachment.content` (PostgreSQL, not S3: the production media bucket serves public URLs) | 365 days after the ticket closed |
| Bodies of automated mail / of spam | | 90 / 30 days after arrival |
| Tickets (number, subject, requester, dates, audit trail) | `helpdesk.Ticket`, `TicketEvent` | 1,095 days after closing |
| Replies and acknowledgements sent (text as written, recipients, delivery state) | `helpdesk.TicketMessage` (`kind=reply`) | Like the ticket's other message bodies |

The inbound queue row also keeps what the import made of a message (`result`): its ticket and, for a reply to the
site's mail, the email it answers (`site_mail`), how that was found (`site_match`: `message_id` or
`recipient_subject`) and the address that email went to (`site_recipient`); for a left-the-organisation notice, the
address it names instead (`named_contact`, `named_contact_kind`), a narrowly extracted name and a US ten-digit / `+1`
phone normalized to E.164 `+1` (international numbers are ignored). Email Monitoring → Bounced addresses counts the
notices from these and copies the unverified contact hints only for its bounded review period
([Email monitoring](email-monitoring.md#counting)). The raw MIME is never kept: the mailbox holds
the original. The worker's hourly maintenance runs the purge
("Helpdesk retention") and restarts the ingest chain if mail waits ("Helpdesk ingest scheduling"). Every helpdesk
model and `core.inboundmessage` are in `safe_orm`'s `DENIED_MODEL_LABELS`: the AI assistant and `/admin-api/` can
neither read nor write them.

**Storing message bodies and attachments is new** for this site (the admin inbox reads them on demand only). The
helpdesk is internal: only staff with the Helpdesk app see it, and no note to OIT or InfoSec is needed (decided
2026-11-11, plan question H6). The retention periods are proposals pending a UC records policy (plan question S5).

## Permissions

The **Helpdesk** app grant (`Member.admin_apps` contains `helpdesk`, or I2G Master) gives everything in the
helpdesk: the queue, ticket pages, notes, replies, assignment, merge, spam, Ingest Problems, assignment groups, SLA
targets, response templates and Settings (shadow mode included). Every custom view (ticket notes, replies, attachment
downloads) checks the grant itself (403 without it). Tickets are created only from
mail; only an I2G Master can delete one by hand, behind the typed confirmation (otherwise only retention deletes).
Opening the linked member or campaign needs the Members or Mail app.

## Settings

Helpdesk → Settings (one row; until it is saved, the defaults apply). The intake card above the form has the
intake's own controls ([Intake controls](#intake-controls)).

| Field | Default | Meaning |
|---|---|---|
| `enabled` | on | Read the Inbox and import its mail. Off: the helpdesk neither reads nor imports; switched back on, the intake continues from its checkpoint, so mail that arrived meanwhile (and is still in the Inbox) becomes tickets then. |
| `shadow_mode` | on | On: nothing is ever sent. Off: replies from the ticket page, and the acknowledgement and notifications below when they are on. |
| `send_acknowledgement`, `acknowledgement_text` | off, a short thank-you naming `{ticket}` | Email the requester when their message opens a new ticket ([Replies and notifications](#replies-and-notifications)). |
| `notify_assignment` | on | Email staff a ticket is assigned to (or their group's members). |
| `auto_close_resolved_days` | 7 | Resolved tickets close by themselves after this many days (0: never). |
| `sla_warning_percent` | 75 | A running SLA clock is shown as at risk once this share of its time is used. |
| `pause_while_campaign_sending` | on | Wait while a campaign is sending. |
| `ingest_batch_size`, `ingest_max_seconds`, `max_attempts` | 100, 60, 5 | Budget of one run; attempts before a message is listed under Ingest Problems. |
| `message_max_bytes`, `attachment_max_bytes` | 25 MB, 10 MB | Most of one message read (also capped by `GRAPH_INBOX_MESSAGE_MAX_BYTES`); largest attachment stored. |
| `body_text_max_chars`, `body_html_max_chars` | 256 KB, 1 MB | Longer bodies are cut ("open the original in Outlook"). |
| `blocked_extensions`, `warn_extensions` | see the model | File types never stored; file types downloaded after a warning. |
| `reopen_window_days` | 14 | A reply within this many days after closing reopens the ticket. |
| `flood_threshold`, `flood_window_minutes` | 10, 60 | Grouping of many new tickets from one sender. |
| `spam_scl_threshold` | 5 | Exchange spam confidence level from which mail is spam. |
| `bulk_bcl_threshold` | 7 | Exchange bulk complaint level from which mail is list or bulk mail (Exchange Online's own default bulk threshold); never on its own for a reply to the site's mail. |
| `reply_match_window_days` | 30 | How long after an email the site sent without a Message-ID (one carrying a sign-in link) a reply to it is recognised by its sender and subject (at most 180, the telemetry's retention). |
| `backfill_age_hours` | 24 | Mail imported later than this after it arrived is marked backfilled. |
| `automated_retention_days`, `spam_retention_days`, `closed_body_retention_days`, `attachment_retention_days`, `ticket_retention_days` | 90, 30, 730, 365, 1095 | Retention (above). |

The intake's cadence and bounds are settings (`EMAIL_MONITORING` in
`src/config/settings/base/integrations/email/email_monitoring/__init__.py`), like bounce processing's: they bound the
controls on the card, so they are not edited beside them.

| Setting | Default | Meaning |
|---|---|---|
| `inbox_scan_interval_seconds` | 120 | Time between intake scans (never under 60 s; 30 s while catching up). |
| `inbox_initial_lookback_hours` | 72 | How far the first intake scan looks back, unless the first-scan lookback is set on the card. |
| `inbox_max_lookback_days` | 90 | The furthest back **Rescan since** and the first-scan lookback reach. |
| `bounce_scan_page_size`, `bounce_scan_max_pages`, `bounce_scan_overlap_seconds`, `bounce_scan_max_seconds`, `bounce_lease_seconds` | 50, 10, 900, 60, 900 | The listing bounds, shared with the bounce scan. |

## Intake controls

The **intake card** sits above the Helpdesk → Settings form. It shows the intake's state (running, paused, waiting
for the first scan, last scan failed, no recent successful scan, switched off, or not active with the reason), the
last and next scan, the checkpoint, the interval and how many messages wait to be imported, and has four controls.
Each needs the Helpdesk app, is a POST form with CSRF (`/admin/helpdesk/helpdesksettings/intake/`, `action=scan`,
`pause`, `resume`, `rescan&since=YYYY-MM-DDTHH:MM`, or `lookback&lookback_hours=N`), and changes the intake only:
bounce processing has its own card on Email Monitoring, and its Pause, Rescan since and lookback never change the
intake. Every change leaves an admin history line (Site Settings → Admin Log, on "Helpdesk intake for …") and a log
line (`helpdesk_intake_state action=…`).

- **Scan now** queues an intake scan at once (otherwise one runs every 2 minutes). Not while paused or off.
- **Pause intake / Resume intake.** Paused, the helpdesk neither lists the Inbox nor imports mail already recorded
  (it makes no Microsoft request at all); its checkpoint stays, so resuming continues from there and nothing is
  missed. Resuming also wakes the import of mail that waited. It works while the mailbox cannot be read, like the
  lookback. To switch the helpdesk off for good, use `enabled` instead.
- **Rescan since** (a date and time in the site's time zone, `America/Los_Angeles`) moves the intake's checkpoint
  back, so that its next scan lists the Inbox again from that time (less the 15-minute overlap): mail from before
  the helpdesk ran, or before the first scan's lookback. Messages already recorded are skipped (one row per Graph
  id), and a message whose queue row was purged meanwhile is recognised by its Message-ID, so no ticket is made
  twice. It starts no scan, and is refused, with the reason, when the time is in the future, more than
  `inbox_max_lookback_days` (90) days ago, not before the current checkpoint (nothing changes; repeating a rescan is
  harmless), or does not exist or occurs twice in the site's time zone; also while an intake scan holds the
  intake's lease (try again a minute later). A scan reads its checkpoint only once it holds the lease, so a rescan
  is never lost to a scan starting at the same moment, and an expired lease is released so the stalled scan that
  held it saves nothing. A paused intake stays paused, and a switched-off helpdesk stays off: the rescan takes
  effect when it runs again. Mail deleted or moved out of the Inbox cannot be read again.
- **First-scan lookback** (hours) sets how far back the intake's *first* scan reads, while it has no checkpoint: 1
  hour to `inbox_max_lookback_days` (2,160 hours); empty restores the default, `inbox_initial_lookback_hours` (72).
  Once the intake has a checkpoint it is no longer used: use **Rescan since**.

There is no change form for the intake's state row (`helpdesk.IntakeState`, one per mailbox) on purpose: a form
saves every column and would overwrite a running scan's lease.

## Deployment

1. Migrations `core.0046_inbound_message` (the queue table), `helpdesk.0001_initial` (the helpdesk tables and,
   on PostgreSQL, the ticket number sequence), `helpdesk.0002_intake_state` (the intake's state table) and
   `helpdesk.0003_reply_detection_settings` (`bulk_bcl_threshold` and `reply_match_window_days`, with database
   defaults for the rolling deploy). No data migration: messages imported before the release keep their verdicts.
   `helpdesk.0004_servicedesk` adds the ServiceNow-style fields (impact, urgency, assignment group, SLA clock,
   resolution, reply delivery state), the Assignment Group, SLA Target and Response Template tables and the new
   settings, all with database defaults for the rolling deploy, and seeds the four SLA targets. Existing tickets keep
   their priority, start at impact and urgency 2, and have no SLA clock. Shadow mode stays as it was saved (on).
2. The background worker (`itg-background-worker`) and `BACKGROUND_JOBS_ENABLED` are required: the scan and the
   import are background jobs. Nothing happens without them.
3. The Microsoft Graph mailbox scope must grant **read** on the sending mailbox, as for bounce processing. No new
   Graph permission and no allow-list change: the import uses the same two GET requests (list the Inbox, read a
   message's `$value`). `ALLOWED_REQUESTS` is unchanged; a test pins it.
4. The worker's first maintenance run starts the intake. Within a few minutes, Helpdesk → Queue fills with the
   Inbox's mail of the last 72 hours (the first scan's lookback; mail imported more than 24 hours after it arrived
   opens backfilled tickets). Use **Rescan since** on the intake card for older mail.
5. To stop reading and importing without a deploy, use **Pause intake** on the intake card (it keeps the
   checkpoint), or switch off **enabled** in Helpdesk → Settings.
6. Before switching shadow mode off: create the assignment groups (and their members), set the categories' default
   groups, review the SLA targets and write the response templates; make sure `BACKEND_URL` is the admin's public
   address (the notification links use it) and that email delivery works (Notification Delivery). Sending uses the
   site's normal email configuration (Graph or SES) on the transactional lane; no new permission is needed.

## Limitations and follow-ups

- **SLA in calendar time only**: no business-hours schedules or holidays, and no breach warning emails (the queue's
  SLA column, the SLA Breached view and the timeline show them).
- **Replies are plain text** (rendered into the branded layout) with no attachments; answers written in Outlook are
  still not seen by the site, so they neither show on the ticket nor stop the response SLA (move the ticket out of New
  instead).
- **No requester portal** or watch list: requesters interact by email only.
- **Mail deleted or moved out of the Inbox before a scan is missed**; only the Inbox is read. With immutable ids
  off (`EMAIL_GRAPH_IMMUTABLE_IDS`), a message moved in Outlook between its listing and its import is skipped as
  gone (Ingest Problems).
- **A very dense Inbox stalls the intake's catch-up** as it does bounce processing's: it lists with the same bounds
  ([Email monitoring, Limitations](email-monitoring.md#limitations)).
- **Inline images are not shown** in the message (they are listed as attachments).
- **Replies are recognised only to mail the telemetry still holds** (180 days) and, for mail sent without a
  Message-ID, only from the address mailed with the same subject, or by a message of a person's ticket they name; a
  reply to older mail, or from another address of the person, is classified on its own headers. So is a first answer
  to an email staff wrote in Outlook (the site never records those), which a CRM tool's bulk headers can still hide
  as bulk mail: check **Automated & Spam**. A reply through a **mailing list** stays list mail (flagged; decision to
  confirm).
- **Notice wording is read in seven languages** (English, Spanish, French, German, Portuguese, Italian, Dutch); in
  others an automatic reply is still recognised by its headers and subject prefix, as "other". A notice's named
  address, narrowly introduced name, and US-only `+1` phone are unverified hints for staff to check, never used on
  their own; international phone numbers are ignored.
- **Graph `conversationId`** can change when an outsider replies, and every reply to one blast may share it; it is
  only a fallback, and only for participants.
- No full-text search over bodies, no link of a ticket to an event or registration, no blocked-sender list (plan
  phases H2/H3).

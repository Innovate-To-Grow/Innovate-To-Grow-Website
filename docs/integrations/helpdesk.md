# Helpdesk (tickets from the i2g@ mailbox), shadow mode

Every message that reaches the Inbox of the site's Microsoft Graph mailbox (`i2g@ucmerced.edu`) becomes a
ticket in the Django admin (**Helpdesk** section), or joins the ticket of its conversation. Automated mail
(out-of-office replies, bounce reports, read receipts, list mail and newsletters, spam, the site's own mail)
also becomes a ticket, but one that is closed at once, hidden from the default queue, never notifies anyone and
never reopens.

The helpdesk ships in **shadow mode**: it reads the mailbox and writes tickets, and **sends nothing**. There is no
reply composer, no acknowledgement and no notification, and nothing in Outlook changes (no mail is marked read,
moved, flagged or forwarded). Staff keep answering from Outlook. The design and the open questions are in the
Item 2 plan (`item2-helpdesk-bounces-plan-2026-11-10.md`, §2, kept with the project notes, not in this
repository), which predates two decisions recorded here: automated mail *is* a ticket (closed and hidden), and
only phase H1 plus merge and spam from H2 is built.

## For staff

| Sidebar entry | What it shows |
|---|---|
| **Queue** | People's open tickets (new, open, pending), most recent activity first. A dot marks an unread customer message. |
| **My Tickets** / **Unassigned** | The same list, assigned to you / to nobody. |
| **Automated & Spam** | Automated mail and spam (all statuses). Use **Not automated: move to the queue** when a person's message landed here. |
| **Ingest Problems** | Messages that could not be imported (after the last attempt) or were gone from the mailbox, with **Retry**. |
| **Categories**, **Settings** | Ticket categories; the helpdesk's limits, retention periods and switches. |

The list filters (**Mail**: people / automated & spam / everything; **Status**; **Assignee**; **Unread**; priority;
category) and the search (a number such as `1234` or `I2G-#1234`, the subject, or the requester's address or
name) narrow the queue.

**The ticket page** edits status, priority, category and assignee (no typed confirmation; every change is in the
ticket's timeline and the admin history), shows the timeline (messages, internal notes, field changes) and has
the internal-note form. Notes are seen only by staff with the Helpdesk app and are never sent. Opening a ticket
marks it read.

- Message HTML was sanitized when it was imported and is shown in a sandboxed frame without scripts; images are
  replaced by `[image]` (remote images would track the reader; inline ones are listed as attachments).
- A message the scam checks found suspicious carries a warning; do not open its links before checking the sender.
- Personal sign-in and subscription links quoted in a message are shown as `[sign-in link removed]`.
- Attachments download as files. Archives (zip, 7z, rar, …) open a warning first; blocked file types
  (executables, scripts, disk images, HTML/SVG, macro-enabled Office files, OneNote, CHM) and files over the size
  limit keep only their name, size and type: open the message in Outlook if you need them.
- Automated messages in a thread are collapsed.

**Bulk actions:** assign to me, unassign, close, reopen (never an automated ticket), mark as read, move to the
queue, and, behind a typed confirmation (`MERGE`, `SPAM`), **merge** (every selected ticket goes into the oldest
one; nothing is deleted) and **mark as spam**.

## How a message becomes a ticket

1. **Recording.** The bounce processor's scan ([Email monitoring](email-monitoring.md)) lists the Inbox
   incrementally and now records every listed message once in `core.InboundMessage` (mailbox, Graph id, internet
   Message-ID, conversation id, received time, sender, scrubbed subject; never a body). While the helpdesk is on,
   the scan runs every `inbox_scan_interval_seconds` (2 minutes) instead of 10, and a scan that recorded new mail
   queues the job `helpdesk.ingest_inbound` (the helpdesk registers itself as the inbound queue's consumer;
   `core` imports no business app). Polling only: no webhooks.
2. **Import** (`apps/helpdesk/services/ingest/`). The job takes due rows, oldest first, within a budget (100
   messages or 60 s per run), and for each: skips it as a duplicate when a ticket already holds its Message-ID;
   reads its raw MIME through the site's Graph reader (GET only, paced on the `graph_read` channel, at most
   25 MB); parses it under the same hardening as bounce reports; classifies it; threads and stores it. A message
   gone from the mailbox is skipped with the reason; a failure is retried with backoff and, after 5 attempts,
   listed under Ingest Problems. A throttle from Microsoft ends the run and the message waits as long as asked.
   While a campaign is sending, the job waits (`pause_while_campaign_sending`): reads and sends share Outlook's
   per-mailbox limits.
3. **Classification** (`apps/core/services/email/inbound/classify.py`, pure): the site's own message (from its
   address *and* proven by DKIM or Exchange's internal marker), bounce or delay report, read or delivery receipt,
   automatic reply (vacation, left the organisation, other), other system mail (calendar replies, quarantine
   notices, auto-generated notices), list or bulk mail, spam (Exchange SCL ≥ 5 or its spam verdict), else human.
   Only strong signals (headers, and the auto-reply subject prefixes mail systems write in several languages)
   make a message automated; **anything uncertain is human**. Content-only signs become hints (flags such as
   `possible_auto_reply`). A human message is also scored by the Mail app's rule-based scam checks (never the
   optional Bedrock review): high → spam, medium → a "suspicious" flag. A message that claims the site's address
   without proof is flagged suspicious.
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
     into the latest one, flagged `flood`.
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
| Listed-message metadata | `core.InboundMessage` | `inbound_retention_days` (90) after processing (`EMAIL_MONITORING`) |
| Message text (personal sign-in links and token-shaped runs scrubbed) and sanitized HTML, capped at 256 KB / 1 MB | `helpdesk.TicketMessage` | 730 days after the ticket closed |
| Attachments (10 MB per file, 25 MB per message; blocked types never) | `helpdesk.TicketAttachment.content` (PostgreSQL, not S3: the production media bucket serves public URLs) | 365 days after the ticket closed |
| Bodies of automated mail / of spam | | 90 / 30 days after arrival |
| Tickets (number, subject, requester, dates, audit trail) | `helpdesk.Ticket`, `TicketEvent` | 1,095 days after closing |

The raw MIME is never kept: the mailbox holds the original. The worker's hourly maintenance runs the purge
("Helpdesk retention") and restarts the ingest chain if mail waits ("Helpdesk ingest scheduling"). Every helpdesk
model and `core.inboundmessage` are in `safe_orm`'s `DENIED_MODEL_LABELS`: the AI assistant and `/admin-api/` can
neither read nor write them.

**Storing message bodies and attachments is new** for this site (the admin inbox reads them on demand only).
Before relying on it, tell OIT/InfoSec (plan question H6); the retention periods are proposals pending a UC records
policy (plan question S5).

## Permissions

The **Helpdesk** app grant (`Member.admin_apps` contains `helpdesk`, or I2G Master) gives everything in the
helpdesk: the queue, ticket pages, notes, assignment, merge, spam, Ingest Problems and Settings. Every custom view
(ticket notes, attachment downloads) checks the grant itself (403 without it). Tickets are created only from
mail; only an I2G Master can delete one by hand, behind the typed confirmation (otherwise only retention deletes).
Opening the linked member or campaign needs the Members or Mail app.

## Settings

Helpdesk → Settings (one row; until it is saved, the defaults apply):

| Field | Default | Meaning |
|---|---|---|
| `enabled` | on | Import new mail. Off: the scan still records mail, which waits until this is switched on again. |
| `shadow_mode` | on (read-only) | Nothing is ever sent. This release has no sending code; the switch is shown, not editable. |
| `pause_while_campaign_sending` | on | Wait while a campaign is sending. |
| `ingest_batch_size`, `ingest_max_seconds`, `max_attempts` | 100, 60, 5 | Budget of one run; attempts before a message is listed under Ingest Problems. |
| `message_max_bytes`, `attachment_max_bytes` | 25 MB, 10 MB | Most of one message read (also capped by `GRAPH_INBOX_MESSAGE_MAX_BYTES`); largest attachment stored. |
| `body_text_max_chars`, `body_html_max_chars` | 256 KB, 1 MB | Longer bodies are cut ("open the original in Outlook"). |
| `blocked_extensions`, `warn_extensions` | see the model | File types never stored; file types downloaded after a warning. |
| `reopen_window_days` | 14 | A reply within this many days after closing reopens the ticket. |
| `flood_threshold`, `flood_window_minutes` | 10, 60 | Grouping of many new tickets from one sender. |
| `spam_scl_threshold` | 5 | Exchange spam confidence level from which mail is spam. |
| `backfill_age_hours` | 24 | Mail imported later than this after it arrived is marked backfilled. |
| `automated_retention_days`, `spam_retention_days`, `closed_body_retention_days`, `attachment_retention_days`, `ticket_retention_days` | 90, 30, 730, 365, 1095 | Retention (above). |

Older mail (before the helpdesk ran, or before the first scan's lookback) is imported with **Rescan since** on
Email Monitoring → Bounce processing (Mail app): the scan reads the Inbox again from that time, and both bounce
records and tickets de-duplicate.

## Deployment

1. Migrations `core.0046_inbound_message` (the queue table) and `helpdesk.0001_initial` (the helpdesk tables and,
   on PostgreSQL, the ticket number sequence). No data migration.
2. The background worker (`itg-background-worker`) and `BACKGROUND_JOBS_ENABLED` are required: the scan and the
   import are background jobs. Nothing happens without them.
3. The Microsoft Graph mailbox scope must grant **read** on the sending mailbox, as for bounce processing. No new
   Graph permission and no allow-list change: the import uses the same two GET requests (list the Inbox, read a
   message's `$value`). `ALLOWED_REQUESTS` is unchanged; a test pins it.
4. Within a few minutes of deploying, Helpdesk → Queue fills with mail received since the scan's checkpoint (less
   the 15-minute overlap). Use **Rescan since** for older mail.
5. To stop importing without a deploy, switch off **enabled** in Helpdesk → Settings.

## Limitations and follow-ups

- **No sending** (by design in shadow mode): replies, acknowledgements, notifications, SLA timers and canned
  responses are phase H2; the `shadow` module holds the switch any sending code must check first.
- **Mail deleted or moved out of the Inbox before a scan is missed**; only the Inbox is read. With immutable ids
  off (`EMAIL_GRAPH_IMMUTABLE_IDS`), a message moved in Outlook between its listing and its import is skipped as
  gone (Ingest Problems).
- **Inline images are not shown** in the message (they are listed as attachments).
- **Graph `conversationId`** can change when an outsider replies, and every reply to one blast may share it; it is
  only a fallback, and only for participants.
- No full-text search over bodies, no link of a ticket to an event or registration, no blocked-sender list (plan
  phases H2/H3).

# Helpdesk (tickets from the i2g@ mailbox), shadow mode

Every message that reaches the Inbox of the site's Microsoft Graph mailbox (`i2g@ucmerced.edu`) becomes a
ticket in the Django admin (**Helpdesk** section), or joins the ticket of its conversation. Automated mail
(out-of-office replies, left-the-organisation notices, bounce reports, read receipts, list mail and newsletters,
spam, the site's own mail) also becomes a ticket, but one that is closed at once, hidden from the default queue,
never notifies anyone and never reopens. A person's answer to the site's own mail stays a person's, even when it
was sent from a CRM or marketing tool.

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
| **Automated & Spam** | Automated mail and spam (all statuses). Use **Not automated: move to the queue** when a person's message landed here. A reply to the site's mail that came through a mailing list is list mail here, flagged **reply to our mail**: read it, and move it to the queue if a person wrote it. There is no merge here: nothing is merged into automated mail or spam. |
| **Ingest Problems** | Messages that could not be imported (after the last attempt) or were gone from the mailbox, with **Retry**. |
| **Categories**, **Settings** | Ticket categories; the helpdesk's limits, retention periods and switches, under the **intake card** (how the helpdesk reads the Inbox: [Intake controls](#intake-controls)). |

The list filters (**Mail**: people / automated & spam / everything; **Status**; **Assignee**; **Unread**; priority;
category) and the search (a number such as `1234` or `I2G-#1234`, the subject, or the requester's address or
name) narrow the queue.

**The ticket page** edits status, priority, category and assignee (no typed confirmation; every change is in the
ticket's timeline and the admin history), shows the timeline (messages, internal notes, field changes) and has
the internal-note form. A merged ticket's status cannot be changed, and **Merged** is not in the Status list: only a
merge makes a ticket merged. Notes are seen only by staff with the Helpdesk app and are never sent. Opening a ticket
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
queue, and, behind a typed confirmation (`MERGE`, `SPAM`), **merge** and **mark as spam**. None of them changes a
merged ticket's status (a merge is final: its messages are on the ticket it was merged into, and so is its mail).

**Merging** puts every selected ticket into the oldest one; nothing is deleted. It never goes into automated mail or
spam (a person's messages would be hidden there), and spam is never merged: when the oldest selected ticket is
automated mail or spam, or another selected ticket is spam, nothing is merged and the reason is shown before the
confirmation is asked for. The rule is the helpdesk service's (`services/tickets.py`), so it holds when the merge
runs too, and `Ticket.clean()` refuses such a merge target for any form. Automated mail merged into a person's ticket
shows there collapsed and changes nothing else on it (not its status, unread mark, participants or last activity),
as when it threads there by itself; the merged ticket stays hidden (still automated, now merged), and later mail of
its thread lands on the person's ticket.

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
3. **Classification** (`apps/core/services/email/inbound/classify.py`, pure): the site's own message (from its
   address *and* proven by DKIM or Exchange's internal marker), bounce or delay report, read or delivery receipt,
   automatic reply (vacation, left the organisation, other), other system mail (calendar replies, quarantine
   notices, auto-generated notices), list or bulk mail, spam (Exchange SCL ≥ 5 or its spam verdict), else human.
   Only strong signals (headers, and the auto-reply subject prefixes mail systems write in several languages)
   make a message automated; **anything uncertain is human**. Content-only signs become hints (flags such as
   `possible_auto_reply`). A human message is also scored by the Mail app's rule-based scam checks (never the
   optional Bedrock review): high → spam, medium → a "suspicious" flag. A message that claims the site's address
   without proof is flagged suspicious. In more detail:
   - **Replies to the site's mail** (`ingest/replies.py`, before classifying): a message whose In-Reply-To or
     References name an email the site sent (the telemetry's `OutboundEmail`, kept 180 days), or, for an email sent
     without a Message-ID the site knows (Graph JSON: campaign mail carrying a sign-in link), a reply from the address
     it went to with the same subject once "RE:", "Automatic reply:" and gateway tags such as "[EXTERNAL]" come off,
     sent at most `reply_match_window_days` (30) before. Such a reply is never list or bulk mail on **weak** signals
     alone: `List-Unsubscribe` and the other unsubscribe headers, an email service provider's or CRM's own headers
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
     "On … wrote:", `>` lines, an original-message banner), so the site's own campaign text, quoted back, never
     decides: an **absence** (out of office, vacation, leave, "until Monday", in English, Spanish, French, German,
     Portuguese, Italian and Dutch) makes it a vacation reply, and only otherwise does wording that the person
     **left** (no longer with, has left, retired, mailbox closed, "ya no trabaja", "ne fait plus partie", "nicht mehr
     im Unternehmen", …) or that nobody reads the mailbox make it a left-the-organisation notice. An out-of-office
     reply is therefore never evidence against an address. A notice's **named address** (a new address or someone to
     contact instead, by the words before it) is kept as a hint, never verified; the sender's, the site's, no-reply
     and report addresses and the address the site mailed are never one.
   - **Loop protection.** Replying to the site's mail never turns an automatic reply into a person's message, so an
     automatic reply to an automatic reply stays automated (it joins its thread and changes nothing). A person's
     message that must not be answered automatically (RFC 3834: it came through a list or a bulk sender, asks for no
     automatic reply, or has no return path) carries the hint `no_auto_response`. `shadow.automatic_reply_allowed` is
     the gate any later acknowledgement or notification must pass: false in shadow mode, for automated mail and for
     such messages.
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
| Message text (personal sign-in links and token-shaped runs scrubbed) and sanitized HTML, capped at 256 KB / 1 MB | `helpdesk.TicketMessage` | 730 days after the ticket closed |
| Attachments (10 MB per file, 25 MB per message; blocked types never) | `helpdesk.TicketAttachment.content` (PostgreSQL, not S3: the production media bucket serves public URLs) | 365 days after the ticket closed |
| Bodies of automated mail / of spam | | 90 / 30 days after arrival |
| Tickets (number, subject, requester, dates, audit trail) | `helpdesk.Ticket`, `TicketEvent` | 1,095 days after closing |

The inbound queue row also keeps what the import made of a message (`result`): its ticket and, for a reply to the
site's mail, the email it answers (`site_mail`), how that was found (`site_match`: `message_id` or
`recipient_subject`) and the address that email went to (`site_recipient`); for a left-the-organisation notice, the
address it names instead (`named_contact`, `named_contact_kind`). Email Monitoring → Bounced addresses counts the
notices from these ([Email monitoring](email-monitoring.md#counting)). The raw MIME is never kept: the mailbox holds
the original. The worker's hourly maintenance runs the purge
("Helpdesk retention") and restarts the ingest chain if mail waits ("Helpdesk ingest scheduling"). Every helpdesk
model and `core.inboundmessage` are in `safe_orm`'s `DENIED_MODEL_LABELS`: the AI assistant and `/admin-api/` can
neither read nor write them.

**Storing message bodies and attachments is new** for this site (the admin inbox reads them on demand only). The
helpdesk is internal: only staff with the Helpdesk app see it, and no note to OIT or InfoSec is needed (decided
2026-11-11, plan question H6). The retention periods are proposals pending a UC records policy (plan question S5).

## Permissions

The **Helpdesk** app grant (`Member.admin_apps` contains `helpdesk`, or I2G Master) gives everything in the
helpdesk: the queue, ticket pages, notes, assignment, merge, spam, Ingest Problems and Settings. Every custom view
(ticket notes, attachment downloads) checks the grant itself (403 without it). Tickets are created only from
mail; only an I2G Master can delete one by hand, behind the typed confirmation (otherwise only retention deletes).
Opening the linked member or campaign needs the Members or Mail app.

## Settings

Helpdesk → Settings (one row; until it is saved, the defaults apply). The intake card above the form has the
intake's own controls ([Intake controls](#intake-controls)).

| Field | Default | Meaning |
|---|---|---|
| `enabled` | on | Read the Inbox and import its mail. Off: the helpdesk neither reads nor imports; switched back on, the intake continues from its checkpoint, so mail that arrived meanwhile (and is still in the Inbox) becomes tickets then. |
| `shadow_mode` | on (read-only) | Nothing is ever sent. This release has no sending code; the switch is shown, not editable. |
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
`src/config/settings/base/integrations/email_monitoring/__init__.py`), like bounce processing's: they bound the
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

## Limitations and follow-ups

- **No sending** (by design in shadow mode): replies, acknowledgements, notifications, SLA timers and canned
  responses are phase H2; the `shadow` module holds the switch any sending code must check first.
- **Mail deleted or moved out of the Inbox before a scan is missed**; only the Inbox is read. With immutable ids
  off (`EMAIL_GRAPH_IMMUTABLE_IDS`), a message moved in Outlook between its listing and its import is skipped as
  gone (Ingest Problems).
- **A very dense Inbox stalls the intake's catch-up** as it does bounce processing's: it lists with the same bounds
  ([Email monitoring, Limitations](email-monitoring.md#limitations)).
- **Inline images are not shown** in the message (they are listed as attachments).
- **Replies are recognised only to mail the telemetry still holds** (180 days) and, for mail sent without a
  Message-ID, only from the address mailed with the same subject; a reply to older mail, or from another address of
  the person, is classified on its own headers. A reply through a **mailing list** stays list mail (flagged; decision
  to confirm).
- **Notice wording is read in seven languages** (English, Spanish, French, German, Portuguese, Italian, Dutch); in
  others an automatic reply is still recognised by its headers and subject prefix, as "other". The named address of a
  notice is whatever its text gives: a hint for staff to check, never used on its own.
- **Graph `conversationId`** can change when an outsider replies, and every reply to one blast may share it; it is
  only a fallback, and only for participants.
- No full-text search over bodies, no link of a ticket to an event or registration, no blocked-sender list (plan
  phases H2/H3).

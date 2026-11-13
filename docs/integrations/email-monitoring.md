# Email Monitoring (telemetry and bounce processing)

Operator runbook for **Mail → Delivery Operations → Email Monitoring**: what the site records about every
outgoing email, how Microsoft Graph bounce reports are read and matched, what each figure on the dashboard
means (and does not mean), the configuration, deployment, retention and access rules, and the limits.

## What it is

- **Telemetry.** Every email the site sends goes through one facade, `apps.core.services.email.deliver_email`
  (sign-in and verification codes, password codes, notifications, admin invitations, event tickets,
  campaigns, inbox replies, the admin test email). The facade records each **logical email**
  (`OutboundEmail`) and each **provider attempt** (`OutboundEmailAttempt`). A new email feature that sends
  through `deliver_email` is recorded with no extra code (category "Other"); wrapping its send in
  `email_tracking(category=...)` files it under its own category. The Graph access check's probe emails, the
  only Graph sends that bypass the facade, are recorded too (category "Graph access check probe") and left out
  of the dashboard's figures.
- **Bounce processing.** Microsoft Graph answers `202 Accepted` when it *queues* a message. A later delivery
  failure comes back as a non-delivery report (NDR) or delivery status notification (DSN) in the sending
  mailbox (`i2g@ucmerced.edu`). The background worker reads those reports, read-only, and records one
  `EmailBounce` per failed or delayed recipient, matched to the email it reports on when a reliable
  identifier allows it.
- **Dashboard.** Overview figures by level, trends, breakdowns, an email log with server-side search, filters,
  sorting and pagination, each email's full history, the bounce reports (including unmatched ones), and a
  page per broadcast campaign (also reached from a sent campaign's **Delivery monitoring** button).

## Statuses: what is and is not known

| Shown | Means | Does not mean |
|---|---|---|
| **API accepted** | The provider accepted the message for delivery (Graph: HTTP 202). | That it reached the mailbox. Nothing on the site ever says "delivered". |
| **API failed** | The provider refused it (4xx, a throttle, an authentication failure) or could not be reached; nothing was queued. | — |
| **API outcome unknown** | The response was lost after the request began, Graph answered 5xx, or Exchange pushed back: it may have been sent, so it is never retried automatically. | Failure. |
| **Not sent** | The site stopped it before calling the provider: configuration or mailbox scope, the delivery-rate limits, a message that could not be composed, a lost job claim. | — |
| **Delivery status unknown** | Accepted, and no bounce report has been matched. | Delivery. A report may come later, or may not be matchable. |
| **Delivery failure confirmed** | A matched bounce report says delivery failed (hard, soft, rejected or unknown). | — |
| **Delivery delayed** | A matched delay notice: the receiving side is still retrying. | Failure (yet). |

Figures are kept apart by level: **messages** (one per logical email, however many attempts), **recipients**
(To, Cc and Bcc of those messages; bounced recipients from matched reports) and **API attempts** (every
provider call, retries included; 429 incidents and response times are attempt figures).

## How the telemetry works

- `EmailDeliveryService.send` wraps each call in a `DeliveryTracker`
  (`apps/core/services/email/telemetry/`). It finds or creates the logical email, opens an attempt once the
  delivery-rate limiter admits the message, and closes both from the outcome. The Graph provider notes each
  step (compose, token, sendMail) and Microsoft's answer: HTTP status, `error.code` and `innerError.code`,
  `request-id`, `client-request-id`, `Retry-After`, the response time and Microsoft's diagnostic headers
  (`x-ms-ags-diagnostic`, throttle scope). Each sendMail now carries a fresh `client-request-id` GUID, which
  Microsoft logs with the request, so even a request whose response was lost can be traced with Microsoft
  support.
- **Retries group by a retry key.** The background worker files each job's email under the job
  (`job_tracking`), and a campaign recipient under its recipient log, so a job that runs again, the
  in-process runner's resend after a throttle, or a resumed recipient add attempts to the same email. A send
  without a key (a sign-in code: asking again issues a new code) is a new email each time.
- **Deferrals are not attempts.** When the delivery-rate limiter holds a message back before any provider
  call, the email's deferral count goes up; nothing reached Microsoft.
- **Recording never changes sending.** Every write is best effort, in its own savepoint: a failure is logged
  with its exception type only and the send continues unchanged. Sending behaviour, the rate limiter and the
  retry rules are untouched; the only change to a request is the `client-request-id` header.
- **What is stored.** Recipients, the subject (truncated to 255 characters, token-shaped text scrubbed;
  switchable off), category, campaign, source record and job ids, the MIME `Message-ID`, statuses, timings, and
  the classified error text the site itself generated (scrubbed of anything token-like). The subject of mail
  that carries a credential (`keep_sent_copy=False`: codes, sign-in links, invitations, tickets, campaign
  messages with the recipient's login link — a campaign *subject* may hold that link) is never stored, only its
  SHA-256 digest for bounce matching, and a bounce report matched to such an email keeps no original subject
  either. Never a message body, attachment, access token, certificate, private key or free text from
  Microsoft's error bodies.

## How bounce processing works

1. **Schedule.** Job kind `core.email_bounce_scan` runs in the background worker. Each scan queues the next
   (every `bounce_scan_interval_seconds`, default 10 minutes, never under a minute; after 2 minutes when it
   stopped at its message budget; later when Microsoft sent a longer `Retry-After`). The worker's hourly
   maintenance ("Email bounce scan scheduling") restarts the chain at start-up or if it broke. **Scan now** on the
   dashboard queues one at once; while processing is paused, switched off or cannot read the mailbox it queues
   nothing and says why (the card greys the button out or hides it then). Finished scan jobs older than a week are
   deleted. The card shows the interval and
   the catch-up the scans really follow (it reads them from the code that schedules them), and lists every other
   app that reads the same Inbox on its own schedule, with its cadence, state and a link to its own controls: the
   [helpdesk](helpdesk.md)'s intake, every 2 minutes (`inbox_scan_interval_seconds`).
2. **Which mailbox.** Only the Graph sending mailbox, only when it is in `EMAIL_BOUNCE_MAILBOXES` (default
   `i2g@ucmerced.edu`) **and** the Graph mailbox scope grants it read permission. Otherwise the dashboard
   shows why processing is not active. No additional Graph permission is used: the reads are the same GET
   requests as the admin inbox (`mailFolders/inbox/messages` and a message's `$value`), which the Graph
   transport's allow-list already permits; nothing is marked read, moved or deleted.
3. **Incremental listing.** Each scan lists Inbox messages received since its durable checkpoint (less a
   15-minute overlap), oldest first, 50 per request, at most 10 requests; the first scan looks back 72 hours (or
   the mailbox's first-scan lookback set on the dashboard; see [Reading older mail again](#reading-older-mail-again)).
   Bounce processing records nothing else: the [helpdesk](helpdesk.md) lists the same Inbox with its own scan
   (its intake: own checkpoint, lease, pause and **Rescan since**), which fills the inbound queue
   (`core.InboundMessage`). Neither one's controls move the other.
   It opens (raw MIME, at most 256 KB, at most 200 per scan, and for at most 60 seconds per scan) only messages
   that look like reports: a report subject prefix (`Undeliverable:`, `Delivery Status Notification`, …) or a
   report sender (`postmaster`, `mailer-daemon`, `MicrosoftExchange…`). The checkpoint moves past what was fully
   processed. Scans share the background worker with every queued email, so these bounds keep a flood of reports
   from holding it.
4. **Parsing.** RFC 3464 `message/delivery-status` parts give, per recipient, the original or final
   recipient, the action, the enhanced status code, the diagnostic code and the remote server; the report
   gives the reporting server and arrival date; the returned headers (`text/rfc822-headers` or
   `message/rfc822`, else the report's `In-Reply-To` and subject) give the original `Message-ID` and subject.
   An old-style bounce without that part is read from `X-Failed-Recipients` and the one text line carrying a
   status code. A person's email that only mentions a bounce is ignored. Anyone can mail the mailbox, so the
   input is treated as hostile: parsing uses the `compat32` policy, every header is cut to 998 characters before
   it is decoded, at most 50 recipients are read per report, texts are read only up to 64 KB, and a report the
   database refuses is skipped and counted instead of blocking later scans.
5. **Classification**: each failed or delayed recipient gets a **category** (what went wrong) from its SMTP reply
   code and enhanced status code, the diagnostic text refining only a generic code, and the coarse classification
   (hard, soft, rejected, delayed, unknown) derived from the category. See [Bounce categories](#bounce-categories).
6. **Matching, without guessing.** *Exact*: the report quotes the original `Message-ID` and a recorded email
   carries it (every MIME send). *Inferred*: no `Message-ID` can match (Graph's JSON form, used for mail that
   carries a credential, returns none) and exactly one recorded email went to the same recipient with the same
   subject in the 120 hours before the report. An email whose `Message-ID` the site knows is never inferred
   for a report quoting a different one (that report is about another message, for example one staff sent
   from Outlook). Anything else stays **unmatched** and is listed as such.
7. **Idempotency.** Each (mailbox, report `Message-ID` or Graph id, recipient) is stored once (unique key), so
   the overlap, a retried scan, two workers or a report moved between folders never add a second row. A
   lease on the mailbox's state row lets only one scan run at a time; an expired lease is taken over.
8. **Throttling.** Every read is admitted on the `graph_read` delivery channel, which shares cooldowns with
   the mailbox's sends: a 429 or a cooldown ends the scan early with its progress kept, and the next scan
   waits at least as long as Microsoft asked. A failed scan (403, 5xx, network) is recorded on the state row
   and shown on the dashboard with the count of consecutive failures.

A matched bounce changes only the email's **delivery status** (its API status stays "accepted"). The site does
**not** resend, suppress or unsubscribe anyone because of a bounce, and does not change the campaign's recipient
log: those are business decisions for staff, made on the **Bounced addresses** page (below).

### Bounce categories

`apps/core/services/email/bounces/classify.py`, with its tables in `bounces/rules/codes.py` (status codes) and
`bounces/rules/phrases.py` (diagnostic phrases). Only **Address does not exist** and **Mailbox disabled** are evidence
against an address; everything else is temporary, about our own sending, about the recipient's policy, or unclear.

| Category | Coarse classification | Decided by (examples) | What it means |
|---|---|---|---|
| **Address does not exist** (`hard`) | Hard bounce | `5.1.1`, `5.1.2`, `5.1.3`, `5.1.6`, `5.1.10`; `5.4.1` (Exchange: no such recipient in the tenant), `5.4.4`, `5.4.310`; text such as "user unknown", "no such user", "does not exist", "doesn't have a … account" on a generic code | Strong evidence: mark it undeliverable or replace it. |
| **Mailbox disabled** (`mailbox_disabled`) | Hard bounce | `5.2.1` (unless its text makes it temporary, see Rules); text such as "account is disabled", "inactive mailbox", Yahoo's `554.30`; a **0 KB size limit** | Strong evidence: replace the address, or mark it undeliverable. |
| **Mailbox full** (`mailbox_full`) | Soft bounce | `5.2.2`, `4.2.2`; "over quota", "mailbox full" | Temporary: counts toward the repeated-failure threshold only. |
| **Temporary failure** (`transient`) | Soft bounce | every other `4.x.x`; `5.4.x` expiry, DNS and connection codes (`5.4.300`, `5.4.312`, `5.4.316`, `5.4.7`, `5.4.14` …); `5.3.x`, `5.6.x`, `5.2.3`/`5.3.4` (message too large); text such as "connection timed out", "connection refused", "DNS query failed", "try again later" on a generic code, or Gmail's "receiving mail at a rate" on a `5.2.1` | The address is probably fine; Exchange already retried. Counts toward the threshold only; the next campaign tries again. |
| **Spam or reputation rejection** (`spam_rejected`) | Rejected | `5.7.9` (Yahoo "policy reasons"), `5.7.20`–`5.7.29` (SPF, DKIM, DMARC, reverse DNS), `5.7.350`, `5.7.501`–`5.7.503`, `5.7.506`–`5.7.509`, `5.7.511`, `5.7.513`, `5.7.606`–`5.7.649`, `5.7.700`–`5.7.749`, `5.7.750`, `5.1.7`/`5.1.8` (our sender address); text such as "spam", "block list", "reputation", "Spamhaus", Yahoo `TSS04` | **Our sending side:** reputation, sender authentication or content. Not the contact. |
| **Relay denied** (`relay_denied`) | Rejected | `5.7.54`, `5.7.57`, `5.7.60`, `5.7.64`; text such as "relay access denied", "unable to relay" | **Our sending side:** the sending route or authorisation (connector, sending mailbox, SPF). Not the contact. |
| **Recipient policy rejection** (`policy_rejected`) | Rejected | any other `5.7.x` (restricted groups `5.7.12`, `5.7.124`, `5.7.133`–`5.7.136`, a generic `5.7.1`); text such as "not authorized", "access denied" | The recipient's server rules; no action on the contact. |
| **Delayed** (`delayed`) | Delivery delayed | the DSN action `delayed` | Still retrying, not a failure. |
| **Unknown failure** (`unknown`) | Unknown delivery status | no code; a generic code (a bare `5.0.0`, Exchange's `5.0.350` "remote server returned an error") or an unrecognised one with no recognisable reason | Unclear: counts toward the threshold only. Read the diagnostic. |

**Rules.**

- **Specific codes win.** The diagnostic text refines only a generic code (`x.0.x`, `x.y.0`, `5.5.x`, `5.7.1`, `4.7.x`)
  or a report with no code, so a spam word can never turn a `5.1.1` into a rejection, and an expiry code is never read
  as a missing address. `5.2.1`, `5.4.1` and `5.4.4` (used for more than one thing) may only be made temporary by
  the text: Gmail returns `5.2.1` both for a disabled account and for a recipient "receiving mail at a rate that
  prevents additional messages from being delivered", a receiving limit that typically lifts within a day.
- **A temporary `4.x.x` is never a missing address or a disabled mailbox**, whatever the text says; text may only make
  it a spam or relay rejection or a full mailbox.
- **A generic status quoting a specific code**: a report whose status is generic (`5.0.0`) but whose diagnostic quotes
  the receiving server's specific code of the same class (`550 5.1.1 …`) is decided by that code.
- **A 0 KB size limit is a disabled mailbox.** A "message too large" report (`5.2.3`, `5.3.4`, or a generic code with
  size wording) whose diagnostic gives a maximum size of 0 (servers disable a mailbox that way) is **Mailbox disabled**;
  any other size limit is a temporary message problem.
- **Yahoo.** "This user doesn't have a yahoo.com account" is a missing address, "This mailbox is disabled (554.30)" a
  disabled mailbox, and "Message not accepted for policy reasons" (`5.7.9`, `PH01`) a spam or reputation rejection;
  a bare `554 delivery error` with no reason (or Exchange's `5.0.350` wrapping one) is **unknown**.
- **Phrase order** when a generic code's text matches several: relay, spam or reputation, disabled mailbox, missing
  address, full mailbox, message too large, temporary, policy. A sender-side rejection is checked first, so text
  naming both spam and a missing address is never strong evidence against the address.
- "Mailbox unavailable" alone is **not** a missing address: RFC 5321 gives it for policy refusals too.
- The phrases follow Exchange Online, Gmail, Yahoo and gateway wording and are matched case-insensitively against at
  most 1,000 characters with bounded patterns, so hostile input stays linear. **Tune them from real reports**: filter
  Bounce Reports by category (for example *Unknown failure*) and read the diagnostics.

**Stored per report:** `category`, `smtp_code` (the reply code, such as `550`), the derived `classification`,
`is_permanent` (whether the address itself will not work: true for a missing address or a disabled mailbox, false for
the rest, empty when unknown) and the reason shown. An email's worst classification (hard, rejected, soft, unknown)
is still kept on the email.

### Reading older mail again

The **Bounce processing** card on the overview has a folded section, **Read older mail again**, with two controls.
Both need the Mail app, are POST forms with CSRF, start no scan, and leave an admin history line (Site Settings →
Admin Log, on the mailbox's "Bounce processing for …" state) plus a log line (`email_bounce_state action=…`). Like
**Pause**, they change bounce processing only: the helpdesk's intake reads the same Inbox from its own checkpoint
and has the same controls on its own card (Helpdesk → Settings; see the [helpdesk](helpdesk.md#intake-controls)).

- **Rescan since** (a date and time in the site's time zone, `America/Los_Angeles`) moves the mailbox's checkpoint
  back, so that the next scan (the scheduled one, or **Scan now**) reads the Inbox again from that time, less the
  usual 15-minute overlap. Use it to backfill: reports that arrived before the first scan (it looks back only 72
  hours), or while the worker was stopped. Reports already recorded are skipped (by Graph id, then by the unique
  key above), so a rescan never adds a second row; it only costs reads, at the usual budgets per scan. It is
  refused, with the reason, when the time:
  - is in the future;
  - is more than `bounce_max_lookback_days` (90) days ago, or beyond `bounce_retention_days` if that is shorter
    (older reports would be purged within the hour);
  - is not before the current checkpoint (that would move it forward and skip mail; nothing changes);
  - does not exist or occurs twice in the site's time zone (a daylight-saving change).

  It is also refused while a scan holds the mailbox's lease (that scan would save its own checkpoint over the new
  one; try again a minute later). A scan reads its checkpoint only once it holds the lease, so a rescan is never
  lost to a scan starting at the same moment, and an expired lease is released so the stalled scan that held it
  saves nothing. A paused mailbox stays paused: the rescan takes effect when processing is resumed. Mail deleted
  or moved out of the Inbox cannot be read again.
- **First-scan lookback** (hours) sets how far back the *first* scan of the mailbox reads, while it has no
  checkpoint: 1 hour to `bounce_max_lookback_days` (2,160 hours). Empty restores the default,
  `bounce_initial_lookback_hours` (72). Once the mailbox has a checkpoint the lookback is no longer used; use
  **Rescan since** instead. The lookback stays editable while processing is not active, like Pause.

## Bounced addresses

**Email Monitoring → Bounced addresses** (`/admin/mail/email-monitoring/addresses/`) lists every address a bounce
report or an Amazon SES bounce or complaint named, one row per address (`mail.BouncedAddress`), with what staff may
do about it. **Nothing on it happens on its own:** counting never changes a member, a contact email or a
subscription, and every change is a staff action with a confirmation page and an audit record.

### Counting

- **Sources.** Microsoft Graph bounce reports (`core.EmailBounce`), each counted once, by coarse classification (hard,
  soft, rejected, delayed, unknown) and by [category](#bounce-categories) (`BouncedAddress.category_counts`, with the
  latest report's `last_category`). Amazon SES events on campaign recipient logs (`RecipientLog`): permanent (shown as
  hard), transient (soft) and undetermined (unknown) bounces, and spam **complaints**. "Left the company" auto-replies
  are not counted yet: they need the helpdesk's inbound queue.
- **Reports without a category** (saved by the previous release while a deploy rolled out) are classified before each
  Graph batch is counted. A **parked** Graph cursor (far in the future: no report is past it, so a release that
  predates categories counts nothing) makes the next count start the Graph counts again from the stored reports,
  recorded as an automatic rebuild. `mail.0026` parks it (see Deployment), and so does the hourly refresh when an
  address's Graph counts by classification and by category do not add up to the same number (every report counted by
  this release adds one to each, so only a report counted by the previous release during a rollout can cause that).
- **Kept after purges.** Counts are stored on the row, so they outlive the 365-day bounce retention; a deleted
  campaign keeps its SES counts too.
- **Incremental and exactly once.** Each source is read from a stored cursor (`mail.BounceAggregationState`), one
  batch per transaction holding the source's row lock. Reports younger than `address_settle_seconds` wait for the next
  run, so a report whose transaction commits late is never skipped. Counting runs when the list page loads (at most
  `address_page_rows` rows, without waiting for another run) and in the background worker's hourly maintenance
  ("Bounced address counting", before "Email telemetry retention").
- **Campaigns.** A matched report gives its email's campaign (exact). For an unmatched one (the blast predates
  telemetry), the one campaign that mailed the address in the matching window before the report is shown as
  *likely*; when several did, none is guessed.
- **Matched reports.** Anyone can mail the mailbox a report-shaped message, so each address also counts the Graph
  reports matched to an email the site sent (exactly or inferred). An address whose reports are all unmatched (and
  with no SES event, which AWS signs) is marked "unmatched", its suggestion says to check the reports first, and the
  **Evidence** filter separates the two.
- **Reopening.** Only strong evidence reopens a dismissed address (queue state only): a report that the address does not
  exist or that its mailbox is disabled, matched to an email the site sent, or an SES permanent bounce or complaint,
  arriving after the dismissal. Temporary failures, rejections (spam, relay, policy), delays and unknown failures
  never reopen anything, and neither does an unmatched report.
- **Rebuild counts…** (I2G Master only) first classifies every stored Graph report again with the current rules (so a
  change to the rules reaches the reports already received), then starts every count again from the records still
  stored (review state, suppressions and the history stay). Counts of purged reports cannot be rebuilt; the
  confirmation page says so. It leaves an audit row (with how many reports changed) and an admin history line.
- **Member links** are re-checked hourly for at most `address_refresh_rows_per_run` addresses per run, continuing
  where the last run stopped, so a very long list is covered over several runs.

### The list and one address

- **Columns:** counts by category (Graph) and by type (SES), first and last report, the latest report's **category**
  with what it means, the last code and reason with the remote server, the member
  (linked for staff who also hold the Members app) with Active / Inactive / Staff badges, the address's **role**
  (primary, secondary, other, unlinked contact, not a contact, or **ambiguous** when one address is saved in several
  letter cases), verified / subscribed / suppression flags, campaigns, review status and a text-only suggestion.
- **Filters:** status tabs (Open by default), type, **category** (has a report of that category; for a missing address,
  a temporary failure and an unknown failure, also the SES permanent, transient and undetermined bounces), role,
  member (has a member, none, active, inactive, staff),
  suppressed, evidence (matched to the site's mail, or unmatched reports only), suggestion, campaign, last-report date
  range and a search on the address or member name; sortable
  columns; **Export these rows (.xlsx)** writes the filtered list (every cell formula-safe, at most
  `address_export_max_rows` rows). Roles and members are read live on every page; the filters use the values last
  refreshed (on each page, after each count and hourly).
- **One address** shows the Graph reports still stored, the SES events, the campaigns, the member card (name,
  status, registrations; their other addresses with their flags, and their phones, only for staff who also hold the
  Members app, as on the Member admin), every action with why it is unavailable, and the history.
- **Suggestions** (never applied; the first that applies wins):

  | Suggestion | When |
  |---|---|
  | Unsubscribe: they reported us as spam | A spam complaint. |
  | Mark undeliverable or replace the address | A report that the address does not exist, or an SES permanent bounce. |
  | Replace the address (the mailbox is disabled), or mark it undeliverable | A disabled-mailbox report. |
  | Consider marking undeliverable (repeated temporary failures) | At least `address_soft_bounce_repeats` temporary failures (temporary, full-mailbox and unknown reports, SES transient and undetermined bounces) over at least `address_soft_bounce_days` days. |
  | Our sending side: relay denied … | A relay refusal and none of the above. |
  | Our sending side: spam or reputation rejection … | A spam or reputation rejection and none of the above. |
  | Their server's policy refused the message, not the address: no action | A policy rejection and none of the above. |

  A temporary failure (a connection timeout, a DNS failure, an expired delivery, a full mailbox) never suggests
  marking an address undeliverable on its own. "Unmatched reports only: check them first" is shown only beside a
  suggestion about the address itself.

### Actions

Every action is a POST (with CSRF) to a confirmation page, then an "apply" POST. Applying re-reads the address, its
contact emails and the member under locks and refuses, changing nothing, when anything changed since the page was
shown. Each applied action writes a `mail.BouncedAddressAction` row (actor, member and address snapshots, role
before and after, note and details; it survives the member's deletion) and an admin history line on the member (or
on the address when it belongs to no member).

| Action | Effect | Undo | Confirmation | Needs |
|---|---|---|---|---|
| Dismiss (reason required) | Leaves the open queue; nothing else changes | Reopen | page | Mail |
| Suppress address (no member) | Every campaign skips it | Clear suppression | page | Mail |
| Mark undeliverable (a member's address) | Every campaign skips it; sign-in codes, tickets and notifications still go | Clear suppression | page | Mail + Members, and the member is manageable |
| Unsubscribe this address | `subscribe` off for this address only | Re-subscribe on the member page | page | Mail + Members |
| Use another address as primary | `make_contact_email_primary` on a verified address the admin picks; the old primary becomes secondary | Swap back once verified | page | Mail + Members |
| Replace email | Adds the new address (valid, unused in any letter case, not an address with a pending admin invitation; primary only when attested verified, which needs an I2G Master on a staff account), then marks the old one undeliverable or deletes it. Sends nothing | Partly | page; typed old address when it is deleted | Mail + Members |
| Delete this email address | `delete_contact_email` after the rules below | No | typed address | Mail + Members (an unlinked contact: I2G Master) |
| Deactivate account | `is_active` off and an unfinished sign-up ended (as the Member admin does); never your own account | Activate on the Members page | page | Mail + Members |
| Delete account | Hard delete of the member: the page lists the cascade (`get_deleted_objects`: event registrations, check-ins, contact emails, login links, …) and recommends Deactivate; never your own account; refused when other records protect it | No | typed primary address | **I2G Master** (the cascade reaches apps other staff may not hold; no other admin page deletes a member with a primary email) |

"Manageable" is `user_can_manage_member`: only an I2G Master changes a staff or superuser account. Typed
confirmations follow `ADMIN_REQUIRE_CONFIRMATION` (on in production). Deleting an address is refused when it is the
member's only address, the primary without another verified address (otherwise the admin picks the new primary), the
member's last verified sign-in contact (email or phone), or an ambiguous address; an ambiguous address allows no
contact or account change at all.

**Bulk:** select rows on the list and choose Dismiss, Reopen, Suppress, Mark undeliverable, Clear suppression or
Unsubscribe. The next page lists every selected address with "will change" or the reason it is skipped, and applies
row by row with the same guards and re-checks. Contact and account changes (delete address, replace, make primary,
deactivate, delete account) are never offered in bulk.

### What suppression stops

Suppression (`BouncedAddress.suppressed_at`, set by Suppress address or Mark undeliverable) is the site's one
bulk-mail suppression list (`apps.mail.services.suppression`). Addresses compare in their bare lower-case form.

- **Every campaign audience** skips a suppressed address when it is resolved (subscribers, all members, staff,
  selected members, event registrants, ticket type, checked-in, no-shows, manual lists; registrant audiences
  compare the attendee email snapshot). The campaign's preview, recipient preview and send confirmation say how many
  recipients were skipped.
- **Sends already queued** check again just before the provider call: a queued job or the in-process runner records
  the recipient as failed with "Not sent: this address is suppressed for bulk mail" and sends nothing.
- **Transactional mail is never suppressed:** sign-in and verification codes, password codes, event tickets,
  notifications and inbox replies still go, since the person may have fixed their mailbox.

## Dashboard entry points

| Page | URL |
|---|---|
| Overview | `/admin/mail/email-monitoring/` (`?range=24h|7d|30d`, or `range=custom&start=YYYY-MM-DD&end=YYYY-MM-DD`; `&provider=graph`) |
| Overview data (JSON) | `/admin/mail/email-monitoring/data/` |
| Email log | `/admin/mail/email-monitoring/emails/` (search, category, API status, delivery, last error, retried, campaign, sort, page size) |
| One email | `/admin/mail/email-monitoring/emails/<uuid>/` |
| Bounce reports | `/admin/mail/email-monitoring/bounces/` (`category`, classification, match method, search on recipient, codes, reason, diagnostic and subject) |
| One campaign | `/admin/mail/email-monitoring/campaigns/<campaign uuid>/`, or **Delivery monitoring** on a sent campaign |
| Bounce processing controls | POST `/admin/mail/email-monitoring/bounce-processing/` (`action=scan|pause|resume`; `action=rescan&since=YYYY-MM-DDTHH:MM`; `action=lookback&lookback_hours=N`, empty for the default) |
| Bounced addresses | `/admin/mail/email-monitoring/addresses/` (status, type, `category`, role, member, suppressed, suggestion, campaign, `start`/`end`, `q`, sort, page size) |
| Bounced addresses export | `/admin/mail/email-monitoring/addresses/export/` (the same filters) |
| One bounced address | `/admin/mail/email-monitoring/addresses/<uuid>/` |
| Bounced-address action | POST `/admin/mail/email-monitoring/addresses/<uuid>/<action>/` (`step=confirm`, then `step=apply` with the page's `fingerprint`) |
| Bulk action / counts rebuild | POST `/admin/mail/email-monitoring/addresses/bulk/`, `/admin/mail/email-monitoring/addresses/rebuild/` |

The pages are a tab of **Delivery Operations** in the Broadcast Delivery section.

## Configuration

`EMAIL_MONITORING` in `src/config/settings/base/integrations/email_monitoring/__init__.py`:

| Key (environment variable) | Default | What it does |
|---|---|---|
| `telemetry_enabled` (`EMAIL_TELEMETRY_ENABLED`) | `true` | Record emails and attempts. A kill switch only. |
| `store_subjects` (`EMAIL_TELEMETRY_STORE_SUBJECTS`) | `true` | Keep subjects; off keeps only a SHA-256 digest (inferred matching still works). |
| `retention_days` / `bounce_retention_days` | `180` / `365` | Telemetry and bounce records older than this are deleted by the worker's hourly maintenance ("Email telemetry retention"), in batches of `purge_batch_size` (1,000). |
| `bounce_processing_enabled` (`EMAIL_BOUNCE_PROCESSING_ENABLED`) | `true` | Run bounce scans. |
| `bounce_mailboxes` (`EMAIL_BOUNCE_MAILBOXES`, comma-separated) | `i2g@ucmerced.edu` | The only mailboxes bounce processing may read. |
| `bounce_scan_interval_seconds` | `600` | Time between scans (a `Retry-After` can only lengthen it). |
| `inbox_scan_interval_seconds` | `120` | Time between scans of the [helpdesk](helpdesk.md)'s intake, its own scan of the Inbox (never under 60 s; 30 s while catching up). It lists with the `bounce_scan_*` bounds below. |
| `inbox_initial_lookback_hours` | `72` | How far the intake's first scan looks back unless its first-scan lookback is set on its card. |
| `inbox_max_lookback_days` | `90` | The furthest back the intake's **Rescan since** and first-scan lookback reach. It bounds those admin controls, so it is set here. |
| `inbound_retention_days` | `90` | Inbound queue rows are deleted this long after they were processed (or recorded, never processed: old mail a rescan records still waits to be imported). |
| `graph_immutable_ids` (`EMAIL_GRAPH_IMMUTABLE_IDS`) | `false` | Send `Prefer: IdType="ImmutableId"` on every mailbox read, so a message moved to another folder keeps its id. Switching it on changes the ids the scans and the admin inbox see once (bounce records and helpdesk tickets still de-duplicate by internet Message-ID). |
| `bounce_scan_page_size`, `bounce_scan_max_pages`, `bounce_scan_max_messages` | `50`, `10`, `200` | Messages per list request, list requests per scan, reports opened per scan. |
| `bounce_scan_max_seconds` | `60` | A scan stops (keeping its progress) after this long; the next one continues. |
| `bounce_max_recipients_per_report` | `50` | Recipients read from one report (a genuine report names at most one message's recipients). |
| `bounce_scan_overlap_seconds`, `bounce_initial_lookback_hours` | `900`, `72` | Overlap before the checkpoint; how far the first scan looks back unless the mailbox's first-scan lookback is set on the dashboard. |
| `bounce_max_lookback_days` | `90` | The furthest back **Rescan since** and the first-scan lookback reach (capped by `bounce_retention_days`). It bounds those admin controls, so it is set here, not beside them. |
| `bounce_message_max_bytes` | `256 KiB` | Most of one report read (the status part comes first). |
| `bounce_lease_seconds` | `900` | Longest a scan holds the mailbox. |
| `bounce_match_window_hours` | `120` | Window of the inferred match. |
| `attempt_stale_seconds` | `900` | An attempt still "in progress" after this is shown as interrupted (outcome unknown). |
| `ndr_subject_prefixes`, `ndr_sender_local_parts` | see the file | How a listed message is recognised as a report candidate. |
| `address_batch_size`, `address_page_rows` | `500`, `1000` | Bounced addresses: rows counted per transaction, and at most this many when the list loads. |
| `address_settle_seconds` | `120` | A report is counted only once it is this old (a late-committing transaction is never skipped). |
| `address_soft_bounce_repeats`, `address_soft_bounce_days` | `3`, `7` | When "consider marking undeliverable" is suggested: this many temporary failures (temporary, full-mailbox and unknown reports, SES transient and undetermined bounces) over at least this many days. A temporary failure never suggests more on its own. |
| `address_export_max_rows`, `address_bulk_max_rows` | `10000`, `500` | Rows in one Bounced addresses export; addresses one bulk action may change. |
| `address_refresh_rows_per_run` | `5000` | Addresses whose member links the hourly maintenance re-checks per run. |

**Pause / resume** on the dashboard stops bounce scans of the mailbox without a deploy (stored on its
`EmailMonitorState`, like the first-scan lookback and the checkpoint that **Rescan since** moves). It does not
stop the helpdesk's intake, which has its own pause. There is no generic admin form for that row on purpose: a
form saves every column and would overwrite a running scan's lease.

## Deployment

1. Deploy as usual: migration `core.0044_email_monitoring` creates the four tables (no data migration, no
   backfill), and `core.0045_email_monitor_lookback` adds the nullable first-scan lookback column (empty: the
   setting's default); `core.0046_inbound_message` adds the inbound queue the [helpdesk](helpdesk.md) fills and
   drains.
   Telemetry starts with the first email sent after the deploy; the dashboard shows that moment
   as "Monitoring began". Bounce reports that arrived before the first scan's lookback are read with **Rescan
   since**.
2. The **background worker** container (`itg-background-worker`) must run: it runs the scans and the retention
   purge. Its first maintenance run queues the first scan.
3. For bounce processing, the active Microsoft Graph configuration's mailbox scope must grant **read** on the
   sending mailbox (`Send and read`), as it already does for the admin inbox. No Entra or Exchange change is
   needed: the app's existing grant (Mail.Send + Mail.ReadWrite) covers the GET requests used.
4. Check **Email Monitoring → Bounce processing** after ~10 minutes: "Running" with a recent successful scan.
5. Migration `mail.0023_bounced_address` adds the four Bounced addresses tables (no data migration). The first page
   load and the worker's next hourly maintenance count the bounce reports and SES events already stored.
6. Bounce categories: `core.0047_email_bounce_category` adds `EmailBounce.category` and `smtp_code` and classifies
   every stored report again (a frozen copy of the rules); each matched email's worst classification is set again.
   `mail.0026_bounced_address_categories` adds the category counts and the new suggestions and, when Graph reports
   were counted before, **parks** the Graph counting cursor far in the future (`aggregate.PARKED`). The release
   still running during the rollout then counts no Graph report, and the first Graph count by the new release (the
   Bounced addresses page, or the worker's hourly maintenance) starts the Graph counts again from the stored
   reports, once, and records it as an automatic rebuild. SES counts, review state, suppressions and the history
   stay; nothing is lost while every report is younger than `bounce_retention_days`. The new columns have database
   defaults, so the previous release keeps saving reports during the rollout; whatever it saves without a category is
   classified before the new release counts it. No manual step is needed; **Rebuild counts…** is there if the counts
   ever look off.

   **Image rollback** (an ECS rollback never reverses DDL): an image from before categories finds every column it
   reads (the new ones have database defaults), but it never unparks the Graph cursor. If it takes over before the new
   release has counted once, its Bounced addresses page counts no new Graph report and says "Not counted yet: none"
   (Bounce Reports still lists them). Press **Rebuild counts…** once on that release. Deploying the new release again
   needs no step: the Graph counts start again at its first count when the cursor is still parked, or after the hourly
   refresh finds counts made without categories (they do not add up).

Access: every page requires the **Mail** app (`Member.admin_apps`, or superuser), like the Delivery
Dashboard; the controls are POST with CSRF. Bounced-address actions that change a contact email or a member also need
the **Members** (`authn`) app and a manageable member (see the actions table). The telemetry tables and the four
Bounced addresses tables are denied to the CLI and the assistant (`safe_orm` `DENIED_MODEL_LABELS`) for reads and
writes, so a suppression can only be set or lifted on the page, under its guards.

## Limitations

- **202 is not delivery.** The site has no positive delivery confirmation for Graph mail: it requests no
  delivery or read receipts, and only failures come back as reports. "Delivery status unknown" is the honest
  state of every accepted email without a matched report.
- **JSON sends have no Message-ID.** Credential mail (codes, sign-in links, invitations, tickets, campaign
  messages with a login link) is sent as Graph JSON, which returns no `Message-ID`; their reports can only be
  matched by inference (unique recipient + subject + time) and stay unmatched when that is ambiguous, such as
  two codes with the same subject to the same person within the window.
- **Exact matching relies on Exchange keeping the MIME `Message-ID`** of a MIME `sendMail`. If a report quotes
  a `Message-ID` the site does not know, that report is left unmatched rather than guessed.
- **Not every failure produces a report.** Some receiving servers accept and then silently drop mail, and
  spam filtering may quarantine without a report. Reports from servers that do not follow RFC 3464 are read
  heuristically and may be recorded as "Unknown delivery status".
- **Reports must reach the Inbox.** A report moved out of the Inbox before a scan (by an Outlook rule or a
  person) is not seen. Only the Inbox is read.
- **A very dense Inbox stalls catch-up.** A scan lists at most `bounce_scan_max_pages` × `bounce_scan_page_size`
  messages (each page repeats the previous page's last one) and starts 15 minutes before its checkpoint, so if
  more than about 490 messages arrived within 15 minutes, later scans cannot get past that window. That is far
  above this mailbox's traffic (sends are paced at 30 a minute); raise `bounce_scan_max_pages` if it ever happens,
  for example during a large **Rescan since**. The helpdesk's intake lists with the same bounds, so the same holds
  for it.
- **Multi-recipient inference uses the first recipient.** An inferred match compares the report's recipient
  with the email's first recipient; Cc'd recipients of JSON sends are matched only exactly.
- **History.** Emails sent before monitoring began are not in the telemetry and nothing is reconstructed.
  A campaign page shows how much of the campaign the telemetry covers and, beside it, the campaign's own
  recipient-log counts as recorded at the time.
- **Categories come from the report's codes and, for generic codes, its wording.** The phrase lists follow the usual
  wording of the big providers and gateways; a server that words a failure differently may land in *Unknown failure*
  (which only counts toward the threshold). Only the delivery-status part is read for a structured report (a "0 KB"
  size limit given only in the human-readable text is not seen), and an old-style bounce whose text has no `x.y.z`
  code stays unknown. Check the diagnostics on Bounce Reports and tune `bounces/rules/phrases.py`; then **Rebuild
  counts…** applies the new rules to the stored reports.
- **Reports can be forged.** Anyone can send the mailbox a message shaped like a bounce report. A forged report
  can only change the dashboard (it cannot resend, suppress or change any campaign record), an exact match
  needs the original `Message-ID` (known only to the email's recipients) and an inferred one the recipient and
  subject; the parsing bounds above keep forged reports cheap.
- **Bounces do not change campaign records or subscriptions.** Acting on a bounce (correcting an address,
  unsubscribing, suppressing) is a staff decision made on the Bounced addresses page; the site makes none
  automatically.
- **Other providers.** SES, SMTP and the Gmail API are recorded at the facade (one attempt per call, error
  kind "Provider error"), without Graph's HTTP-level detail; SES delivery events remain in the SES dashboard
  and the recipient log ([SES event tracking](ses-event-tracking.md)).

## Troubleshooting

| Dashboard shows | Check |
|---|---|
| Bounce processing "Not active: Microsoft Graph is not configured" | The active Graph configuration and its certificate ([Microsoft Graph email](microsoft-graph-email.md)). |
| "… not in the bounce-processing mailbox allow-list" | The sending mailbox differs from `EMAIL_BOUNCE_MAILBOXES`; set the variable if the change is intended. |
| "… does not grant read permission" | Give the mailbox scope **Send and read** for the sending mailbox. |
| "No recent successful scan" | The worker is not running, or every scan is held back (see the last error and the next scan time). |
| "Last scan failed" with `403` | The Exchange restriction changed; run the access check. |
| Many unmatched bounce reports | Reports about mail staff sent from Outlook, mail sent before monitoring began, or ambiguous JSON sends. |
| A report's category looks wrong (for example a timeout shown as anything but *Temporary failure*) | Read its status code and diagnostic on Bounce Reports. A specific code decides on its own; for a generic code, add or adjust the wording in `bounces/rules/phrases.py` (with a test), deploy, then **Rebuild counts…**. |
| Many *Spam or reputation rejection* or *Relay denied* reports | Our sending, not the contacts: check the sending domain's SPF, DKIM and DMARC, block lists, the Microsoft 365 connectors and sending mailbox, and the campaign's content. |
| An attempt "Interrupted: outcome unknown" | The process stopped mid-send (deploy, crash); treat as possibly sent. |
| "A scan of … is running, so the checkpoint was not moved" | Wait for the scan to finish (the card shows "running now"; at most `bounce_lease_seconds`), then rescan again. |
| A rescan reads nothing new | The reports were already recorded (the card's last scan counts them as "already recorded" or "duplicates skipped"), or they were deleted or moved out of the Inbox. |

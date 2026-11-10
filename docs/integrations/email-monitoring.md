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
   (every `bounce_scan_interval_seconds`, default 10 minutes; sooner when it stopped at its message budget;
   later when Microsoft sent a longer `Retry-After`). The worker's hourly maintenance ("Email bounce scan
   scheduling") restarts the chain at start-up or if it broke. **Scan now** on the dashboard queues one at
   once. Finished scan jobs older than a week are deleted.
2. **Which mailbox.** Only the Graph sending mailbox, only when it is in `EMAIL_BOUNCE_MAILBOXES` (default
   `i2g@ucmerced.edu`) **and** the Graph mailbox scope grants it read permission. Otherwise the dashboard
   shows why processing is not active. No additional Graph permission is used: the reads are the same GET
   requests as the admin inbox (`mailFolders/inbox/messages` and a message's `$value`), which the Graph
   transport's allow-list already permits; nothing is marked read, moved or deleted.
3. **Incremental listing.** Each scan lists Inbox messages received since its durable checkpoint (less a
   15-minute overlap), oldest first, 50 per request, at most 10 requests; the first scan looks back 72 hours.
   It opens (raw MIME, at most 256 KB, at most 200 per scan, and for at most 60 seconds per scan) only messages
   that look like reports: a report subject prefix (`Undeliverable:`, `Delivery Status Notification`, …) or a
   report sender (`postmaster`, `mailer-daemon`, `MicrosoftExchange…`). The checkpoint moves past what was fully
   processed. Scans share the background worker with every queued email, so these bounds keep a flood of
   reports from holding it.
4. **Parsing.** RFC 3464 `message/delivery-status` parts give, per recipient, the original or final
   recipient, the action, the enhanced status code, the diagnostic code and the remote server; the report
   gives the reporting server and arrival date; the returned headers (`text/rfc822-headers` or
   `message/rfc822`, else the report's `In-Reply-To` and subject) give the original `Message-ID` and subject.
   An old-style bounce without that part is read from `X-Failed-Recipients` and the one text line carrying a
   status code. A person's email that only mentions a bounce is ignored. Anyone can mail the mailbox, so the
   input is treated as hostile: parsing uses the `compat32` policy, every header is cut to 998 characters before
   it is decoded, at most 50 recipients are read per report, texts are read only up to 64 KB, and a report the
   database refuses is skipped and counted instead of blocking later scans.
5. **Classification** (RFC 3463): `delayed` action → Delivery delayed; `5.7.x` → Rejected; other `5.x.x` →
   Hard bounce, except passing conditions (mailbox full `5.2.2`, too large `5.3.4`/`5.2.3`, expired
   `5.4.7`/`5.4.300`, routing loop `5.4.6`, content `5.6.x`, mail system `5.3.x`) → Soft bounce; a failed
   `4.x.x` → Soft bounce; no status code → Unknown delivery status. "Permanent" follows the status class.
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
log: those are business decisions for staff, made from the failed-recipient lists.

## Dashboard entry points

| Page | URL |
|---|---|
| Overview | `/admin/mail/email-monitoring/` (`?range=24h|7d|30d`, or `range=custom&start=YYYY-MM-DD&end=YYYY-MM-DD`; `&provider=graph`) |
| Overview data (JSON) | `/admin/mail/email-monitoring/data/` |
| Email log | `/admin/mail/email-monitoring/emails/` (search, category, API status, delivery, last error, retried, campaign, sort, page size) |
| One email | `/admin/mail/email-monitoring/emails/<uuid>/` |
| Bounce reports | `/admin/mail/email-monitoring/bounces/` (classification, match method, search) |
| One campaign | `/admin/mail/email-monitoring/campaigns/<campaign uuid>/`, or **Delivery monitoring** on a sent campaign |
| Bounce processing controls | POST `/admin/mail/email-monitoring/bounce-processing/` (`action=scan|pause|resume`) |

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
| `bounce_scan_page_size`, `bounce_scan_max_pages`, `bounce_scan_max_messages` | `50`, `10`, `200` | Messages per list request, list requests per scan, reports opened per scan. |
| `bounce_scan_max_seconds` | `60` | A scan stops (keeping its progress) after this long; the next one continues. |
| `bounce_max_recipients_per_report` | `50` | Recipients read from one report (a genuine report names at most one message's recipients). |
| `bounce_scan_overlap_seconds`, `bounce_initial_lookback_hours` | `900`, `72` | Overlap before the checkpoint; how far the first scan looks back. |
| `bounce_message_max_bytes` | `256 KiB` | Most of one report read (the status part comes first). |
| `bounce_lease_seconds` | `900` | Longest a scan holds the mailbox. |
| `bounce_match_window_hours` | `120` | Window of the inferred match. |
| `attempt_stale_seconds` | `900` | An attempt still "in progress" after this is shown as interrupted (outcome unknown). |
| `ndr_subject_prefixes`, `ndr_sender_local_parts` | see the file | How a listed message is recognised as a report candidate. |

**Pause / resume** on the dashboard stops scans of the mailbox without a deploy (stored on its
`EmailMonitorState`).

## Deployment

1. Deploy as usual: migration `core.0044_email_monitoring` creates the four tables (no data migration, no
   backfill). Telemetry starts with the first email sent after the deploy; the dashboard shows that moment as
   "Monitoring began".
2. The **background worker** container (`itg-background-worker`) must run: it runs the scans and the retention
   purge. Its first maintenance run queues the first scan.
3. For bounce processing, the active Microsoft Graph configuration's mailbox scope must grant **read** on the
   sending mailbox (`Send and read`), as it already does for the admin inbox. No Entra or Exchange change is
   needed: the app's existing grant (Mail.Send + Mail.ReadWrite) covers the GET requests used.
4. Check **Email Monitoring → Bounce processing** after ~10 minutes: "Running" with a recent successful scan.

Access: every page requires the **Mail** app (`Member.admin_apps`, or superuser), like the Delivery
Dashboard; the controls are POST with CSRF. The telemetry tables are denied to the CLI and the assistant
(`safe_orm` `DENIED_MODEL_LABELS`) for reads and writes.

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
- **Multi-recipient inference uses the first recipient.** An inferred match compares the report's recipient
  with the email's first recipient; Cc'd recipients of JSON sends are matched only exactly.
- **History.** Emails sent before monitoring began are not in the telemetry and nothing is reconstructed.
  A campaign page shows how much of the campaign the telemetry covers and, beside it, the campaign's own
  recipient-log counts as recorded at the time.
- **Reports can be forged.** Anyone can send the mailbox a message shaped like a bounce report. A forged report
  can only change the dashboard (it cannot resend, suppress or change any campaign record), an exact match
  needs the original `Message-ID` (known only to the email's recipients) and an inferred one the recipient and
  subject; the parsing bounds above keep forged reports cheap.
- **Bounces do not change campaign records or subscriptions.** Acting on a bounce (correcting an address,
  unsubscribing) is a staff decision; the site makes none automatically.
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
| An attempt "Interrupted: outcome unknown" | The process stopped mid-send (deploy, crash); treat as possibly sent. |

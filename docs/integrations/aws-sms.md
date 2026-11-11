# AWS SMS: opt-outs, quiet hours, links and ticket texts

Operator runbook for the SMS policy the site applies on top of AWS End User Messaging SMS
(`pinpoint-sms-voice-v2`): the opt-out list and its AWS sync, the opt-out footer, quiet hours, the segment and
cost estimate, short links in texts (`/l/<token>`), ticket texts for phone-only registrants, and the short
`/register` link with its QR code. Staff manage it in the admin under **Broadcast Campaigns → SMS Settings** and
**SMS Opt-outs**. Sending itself (credentials, the origination number, pacing and budgets) is unchanged:
[Delivery rates](delivery-rates.md) and **Notification Delivery**.

> **Open item before links go live.** Links in SMS (and with them ticket texts) are **off** by default. Before
> turning them on, confirm that the sending number's 10DLC campaign (or toll-free verification) declares
> **embedded links**, with sample messages on this site's domain. If it doesn't, update the registration first:
> carriers filter or suspend numbers whose texts don't match their registration, and approval can take days to
> weeks. Every link is on this site (`/l/...`); no public link shortener is used.

## Where every SMS goes through

Every text the site sends goes through `apps.core.services.aws.sms_send.send_text_message`: sign-in and
verification codes, the admin test SMS, Broadcast SMS recipients (the background job and the in-process sender)
and ticket texts. Before anything is admitted it asks the opt-out list (`apps.core.services.aws.sms_opt_outs`; the
list lives in the mail app, which registers it from `MailConfig.ready()`). A code request for an opted-out number
is refused even earlier, before it takes a delivery slot, the hourly cap or a unit of the SMS daily budget. The
sign-in and account endpoints answer it like any failed send (503 "Failed to send verification SMS.", as before the
list existed): they are open to anyone, and "this number replied STOP" is no stranger's business. The signed-in
event registration says why (400, `code: phone_opted_out`, "use your email address instead").

## Opt-outs

**STOP stays AWS-managed.** AWS End User Messaging handles STOP and HELP on the number (the default; HELP must
include contact information in the number's keyword settings). The site never replies to texts and has no inbound
SMS endpoint. A number that replied STOP is put on AWS's opted-out list, and AWS refuses any later text to it.

**The site's list** (`SmsOptOut`, admin **SMS Opt-outs**) holds one row per number (E.164) with its source:

| Source | Comes from | Cleared by |
|---|---|---|
| AWS opt-out list (replied STOP) | The hourly sync | The sync, once AWS no longer lists the number (the person opted back in) |
| AWS refused a send (opted out) | A send AWS refused with `DESTINATION_PHONE_NUMBER_OPTED_OUT`, before the next sync | The sync, as above (the next sync confirms it as an AWS row) |
| Staff | A person asked staff to stop texting them (**Add SMS opt-out**) | Staff (**Lift selected staff opt-outs**) |

- Every send path skips an active row; a Broadcast SMS audience leaves the number out ("N recipients skipped: opted
  out of texts" on the previews and the confirmation), and a number found opted out at send time is logged
  **Opted out** in the SMS Log, not "Failed". It counts neither as sent nor as failed.
- When a number opts out, the members' matching contact phones are set to **not subscribed**, once
  (`contacts_unsubscribed_at`). Opting back in (START) clears the row but never subscribes anyone again: the member
  re-subscribes on their account page. A member who subscribes again while the opt-out stands is left as they chose.
- **AWS rows cannot be lifted in the admin**: they end when the person replies START to the number (or an AWS
  account admin removes the number from the opt-out list in the AWS console).

### The sync

`apps.mail.services.sms.opt_out_sync` runs in the background worker's hourly maintenance (and from **Sync with AWS
now** on SMS Opt-outs). It is read-only on AWS's side:

1. `DescribePhoneNumbers` finds the sending number (the configured origination number, else the first active SMS
   number, as sending does) and its `OptOutListName` (AWS's `Default` unless changed). Staff can name a list
   instead (**AWS opt-out list** in SMS Settings).
2. `DescribeOptedOutNumbers` pages through that list (`SMS_POLICY["opt_out_page_size"]` per page, at most
   `opt_out_max_pages` pages, `opt_out_request_timeout_seconds` per call, 3 attempts).
3. Listed numbers are added (or reopened) and stamped as seen. **After a complete read only**, AWS-sourced rows AWS
   no longer lists are cleared; a row learned after the run started, or a staff row, is never cleared. A read that
   hits the page cap is recorded as **Partly read** and clears nothing.

Each run records its outcome on `SmsOptOutSyncState` (shown on SMS Settings and SMS Opt-outs): up to date, partly
read, failed (with AWS's error code), SMS not configured, or turned off.

**IAM for the app's AWS identity:** `sms-voice:DescribePhoneNumbers` (already needed to auto-detect the origination
number) and `sms-voice:DescribeOptedOutNumbers`. Without the second, every run is recorded as failed with
`AccessDeniedException`; sending is unaffected (AWS still refuses opted-out numbers, and each refusal is recorded).

## Opt-out footer

**Add the opt-out footer** (on by default) appends **Opt-out footer** ("Reply STOP to opt out.") on its own line to
each Broadcast SMS and ticket text that does not already say STOP. The footer must say STOP, and should use plain
GSM-7 characters only: one curly quote or emoji makes the whole text UCS-2, which halves what a segment holds.
Sign-in and verification codes use their own template (Notification Delivery), unchanged.

## Quiet hours

No Broadcast SMS or ticket text is sent inside the window (**Quiet from** 20:00 to **Quiet until** 09:00,
America/Los_Angeles by default; a start later than the end spans midnight; the end is local wall time across a
daylight-saving change):

- A campaign started during quiet hours is **queued for their end** (background jobs on); the confirmation says
  so. A queued recipient whose job reaches quiet hours is deferred to their end, its attempt refunded, its log
  reading "Held for SMS quiet hours".
- With background jobs off, the in-process sender cannot wait: a send or **Resume paused recipients** is refused
  during quiet hours with the time they end, and a running send pauses its remaining recipients when they begin
  (resume them afterwards).
- A ticket text is queued for their end; with background jobs off it is skipped during them (the ticket is in the
  member's account).
- Sign-in and verification codes (a person asked for them right now) and the admin's test SMS are never held.

`SMS_QUIET_HOURS_ENFORCED` (settings, on) is the deployment switch; the test settings turn it off so no test depends
on the time of day.

## Segments and cost

AWS bills each message part (segment): 160 GSM-7 characters fit one text (153 per part once split; `€ ^ { } [ ] ~
| \` take two); any other character makes the text UCS-2, 70 per text (67 per part); an emoji counts as two. The
Broadcast SMS form shows a live count under the message (`mail/static/mail/js/sms-composer.js`): encoding,
characters, segments and the estimated cost per recipient, measured with example names, full-length links, line
breaks as the form submits them, and the footer. The send preview and the confirmation show the estimate for the
real recipients (each text measured with its own names) at **Estimated cost per segment (USD)** (default $0.0100,
an estimate: AWS's base price plus carrier fees; check the AWS End User Messaging SMS pricing page and set it).

## Links in SMS

With **Allow links in SMS** on, a Broadcast SMS may use:

| Placeholder | Becomes | Opens |
|---|---|---|
| `{{login_link}}` | a personal one-tap sign-in (when allowed), else the campaign's shared link | the campaign's **Sign-in destination** (after a code sign-in for the shared link) |
| `{{ticket_link}}` | the same kinds | the campaign's event registration page (where the ticket shows), else the account |
| `{{event_link}}` | the campaign's shared link | the campaign's event registration page (needs the campaign's **Event**) |

- A link is `FRONTEND_URL/l/<token>`: 16 random bytes (128 bits, 22 characters, `SMS_POLICY["link_token_bytes"]`),
  so a message stays within 1–2 segments and the URL holds no member, phone or event. Only the token's SHA-256
  digest is stored (`SmsLinkToken`); a shared link keeps its plain token (it signs nobody in) so every recipient's
  text can carry it.
- Every link expires: **Link validity (days)** per campaign (default 3), at most
  `SMS_POLICY["link_max_validity_days"]` (14).
- **Personal sign-in links** are off by default (a recycled phone number could receive someone else's link), and
  only the I2G Master (a superuser) can turn them on. On, a link signs its member in **once**, and only when:
  - the member is active and is not staff or a superuser; and
  - the text goes to **that member's own verified account phone**: a personal link reaches no further than signing
    in with a code texted to the same number. A recipient log pointed at another member, a phone verified only for
    one event registration (it may be a family or lab phone), or any other number gets the shared link instead.
    The token keeps a SHA-256 digest of the number (`phone_digest`), and opening it checks again that the member
    still has that verified phone, so a number removed from the account or moved to someone else stops working.

  Anyone else gets the shared link, which opens the sign-in page (email or phone) and returns to the same page.
- Destinations must pass `is_strict_internal_path` (`apps/mail/redirects.py`), the SPA's own rule: one leading
  slash, no backslash, space or control character, no encoded slash, backslash or line break.
- Opening one: the SPA moves the token out of the address at start-up (`/l/<token>` → `/l`), then posts it to
  `POST /mail/sms-link/`, which answers with a session (personal) or a destination (shared), or a 400 with
  `invalid_link` / `expired` / `already_used` (never whose link it was). It is limited by the request limiter's P0
  `auth-email-link` scope, like the emailed login link.
- Campaign texts are checked before sending: a message with a link placeholder cannot be saved, previewed for
  sending or sent while links are off, and one whose links are turned off after it was queued fails each remaining
  recipient with that reason. **SMS Links** lists every link (never its token) and can revoke them; the
  registration admin's **Revoke login links** also revokes the registration's ticket-text links.

## Ticket texts

With **Text tickets to phone-only registrants** on (needs links in SMS; off by default), a registration without an
email address whose phone is verified (the phone verified for the registration, else the member's verified contact
phone) gets a ticket text when its first ticket is issued. The event app sends `initial_ticket_issued` from the
registration's transaction; the mail app records a `TicketSms` (**Ticket SMS**) and queues `mail.ticket_sms` on the
transactional lane, due when quiet hours end. The text is **Ticket text** (`{{first_name}}`, `{{event_name}}`,
`{{ticket_link}}`) plus the footer; the ticket link signs the registrant in when personal links are on and the text
goes to the registrant's own verified account phone, otherwise it opens the sign-in page and returns to the ticket. An opted-out number is never texted; a link that cannot have
arrived (a definite failure) is revoked. A queueing failure never undoes the registration.

## The short /register link and QR code

`/register` opens **/register leads to** (SMS Settings; default the sign-in page, which takes an email address or a
phone number and creates the account; or an open event's registration page, the account, or a CMS page). The SPA
reads it from `GET /mail/register-link/` (cached 5 minutes, dropped when SMS Settings is saved) and falls back to
the sign-in page. SMS Settings shows the QR code for `FRONTEND_URL/register`, with SVG and PNG downloads for flyers
and slides (`segno`, error level M, 4-module quiet zone).

## Settings

| Setting | Where | Default |
|---|---|---|
| Footer on / text | SMS Settings | on / "Reply STOP to opt out." |
| Quiet hours on / from / until / time zone | SMS Settings | on / 20:00 / 09:00 / America/Los_Angeles |
| Estimated cost per segment | SMS Settings | 0.0100 USD |
| Allow links in SMS / Personal sign-in links | SMS Settings | off / off |
| Ticket texts / Ticket text / Ticket link validity | SMS Settings | off / "Innovate to Grow: you're registered for {{event_name}}. Your ticket: {{ticket_link}}" / 7 days |
| Sync AWS opt-outs / AWS opt-out list | SMS Settings | on / blank (the sending number's list) |
| /register leads to | SMS Settings | `/login` |
| Sign-in destination / Link validity | each Broadcast SMS | `/account` / 3 days |
| `SMS_QUIET_HOURS_ENFORCED` | settings (`config/settings/base/integrations/sms`) | on (off in test settings) |
| `SMS_POLICY` | settings | 16-byte tokens, 14-day maximum validity, 100 per page × 50 pages, 10 s per AWS call |

The opt-out list, its sync state, the SMS settings, SMS links and ticket texts are denied to `safe_orm` (the
assistant and `/admin-api/`): they change only through these pages and the senders.

## Not included

Two-way SMS (texting a keyword to register, inbound replies) is not built: STOP and HELP stay AWS-managed, and the
site has no inbound SMS endpoint.

# Chapter 3: Blasts & email monitoring

How to write, test and send a broadcast email ("blast"), and how to tell afterwards what happened to it.
[Back to the handbook](README.md).

**Needs:** the Mail section (**Broadcast Delivery** in the sidebar; `mail` in the access list). Actions on the
Bounced addresses page that change a member also need the Members section (`authn`).

## 3.1 Before you start

### Who the email comes from

All site email (blasts, sign-in codes, tickets) is sent by one provider, chosen on **Broadcast Delivery → Email
Sending Method**. Today it is Microsoft Graph, sending as **i2g@ucmerced.edu**. Replies, out-of-office notices and
"Undeliverable" bounce reports all come back to that mailbox.

### How long a blast takes

The mailbox has sending limits per minute, per hour and per day (the per-minute and per-day ones come from UC Merced
IT; the hourly ones are Microsoft's standard values), and every sign-in code and ticket the site sends counts
against them too. Campaigns use at most 80 % of the sending rate and stop at 90 % of each limit, so codes and tickets
keep the rest. With the default limits a campaign sends about 19 emails a minute and at most 450 an hour to
addresses outside ucmerced.edu, so a blast to 1,000 people takes two hours or more, and a long list carries on the
next day. Until the web team ticks **Tenant limits confirmed** in the delivery settings, campaigns also stop at 900
recipients a day.

The confirmation page shows the daily limits and warns when your list is larger than campaigns may send in 24
hours. Its time estimate counts only the per-minute rate, so the real send usually takes longer.

### Who receives it

| Audience | Who gets it |
|---|---|
| **All subscribers (subscribed email addresses only)** | Active members, at their subscribed addresses only. With **Send to: Primary email only**, a member whose primary is unsubscribed gets nothing. **Use this for newsletters.** |
| **All active members (subscribed or not)** | Every active member, including people who unsubscribed. Only for messages every member must receive. |
| **Staff Members** | Active staff accounts. |
| **Selected Members** | The members you pick. |
| **Manual Emails** | The addresses you type, one per line, all of them. An address that belongs to an active member gets that member's name and sign-in link; any other address gets an empty name and a link to the sign-in page. |
| **Event Registrants**, **Event Ticket Type**, **Checked-In Attendees**, **No-Shows (Not Checked In)** | People registered for the event you pick (or for one ticket type, or who did or did not check in), at the address they registered with. |

- **Send to** chooses which addresses of each member are used: **Primary email only**, or **All emails (primary +
  secondary + other)**.
- **Exclude audience** removes a second group, for example "All subscribers, except the registrants of the spring
  event".
- Only **All subscribers** respects unsubscribes. The other audiences also reach people who unsubscribed, so use
  them only for messages those people expect (about an event they registered for, for example).
- **All subscribers**, **All active members** and **Staff Members** leave out inactive (deactivated) members.
  **Selected Members**, **Manual Emails** and the event audiences do not check: a deactivated member you pick,
  type in, or who registered for the event still gets the email.
- The recipient list is fixed when sending starts.

### Personal fields and sign-in links

You can write these in the subject or the content; each recipient gets their own value:

| Write | Becomes |
|---|---|
| `{{ first_name }}`, `{{ last_name }}`, `{{ full_name }}` | The recipient's name. |
| `{{ login_link }}` | A personal link that signs the recipient in to their account, then opens the **Post-login destination** (default: their account page). |

A login link works like a password: anyone with it can sign in as that person.

- It stays valid for **Login link validity (days)** (default 7, at most 90).
- It works once, unless you tick **Reusable login links**. Unticking that box later stops reuse of links already
  sent.
- The list action **Revoke login links (invalidate emailed sign-in links)** cancels every link of the selected
  campaigns at once.
- Never forward a test email that contains your own link.

**Include one-click unsubscribe** (on by default) adds an "Unsubscribe from newsletters" link to the footer of
recipients who have an account.

## 3.2 Write and send a blast

1. Go to **Broadcast Delivery → Broadcast Campaigns** (tab **Broadcast Email**) and click the **+** (add) button.
2. **Audience:** choose the **Audience type** and, depending on it, the event, ticket type, members or addresses;
   then **Send to**, and an **Exclude audience** if needed.
3. **Campaign:** fill in the **Subject**, the **Post-login destination**, **Login link validity (days)**,
   **Reusable login links** and **Include one-click unsubscribe**. Choose the **Email format** (**HTML** or **Plain
   Text**) and write the **Email Content**. To reuse a design prepared in Gmail, send it from the I2G Gmail account
   set up for the import (**Import Gmail HTML** lists that account's five most recent *sent* messages, not drafts),
   save the campaign, and use **Import Gmail HTML**.
4. **Save**, check the summary of changes and type the confirmation word the page shows.
5. Click **Preview Email** to see the message (with sample name data) and **Preview Recipients** to check who will
   get it and how many.
6. **Test it on yourself first** (see below).
7. Click **Send Campaign**, check the preview, then **Proceed to Send**. The confirmation page shows:
   - the number of recipients;
   - how many recipients have no account, so their `{{ login_link }}` becomes a link to the sign-in page;
   - how long sending will take and the daily limits;
   - (coming soon) how many recipients are skipped because their address is marked undeliverable.
8. Type the campaign's name exactly as shown and click **Confirm & Send**.
9. Follow the progress on the status page or in the campaign list. **Status** goes from **Draft** to **Queued**
   (when the background worker sends; otherwise straight to **Sending**), **Sending**, then **Sent**. **Partially
   sent** means some recipients failed, were paused, or are **Uncertain delivery**; **Failed** means none went.

### Test on yourself first

A campaign cannot be "test sent" from its page. Instead:

1. Make the campaign with **Audience type: Manual Emails** and your own address (and a colleague's) in the list.
2. Send it as above and check the message in your inbox, on a computer and on a phone: layout, links, names, and
   that the unsubscribe link opens its page (do not confirm it there: that would unsubscribe every address of your
   own account). Your copy holds your own sign-in link; do not forward it.
3. On that campaign, click **Duplicate campaign**, keep the same audience, and open the new draft.
4. Change the audience to the real one, preview, and send.

### After sending

- A campaign that has left **Draft** is locked: its subject, content and audience cannot change. To send it again,
  send a corrected version, or send it to more people, use **Duplicate campaign**. Addresses that already received
  the original are not left out automatically: list only the new addresses, or use **Exclude audience**.
- **Broadcast Campaigns → Email Log** shows every recipient with their status.
- Recipients held back by the limits normally wait (**Retry scheduled**) and go out later by themselves. **Paused by
  delivery limits** appears only when the web server itself sends the campaign (when the background worker is not
  running): select the campaign and run **Resume paused recipients (held back by delivery limits)** later, and tell
  the web team.
- A recipient marked **Uncertain delivery** may have received the email. It is never resent automatically; ask the
  web team before sending it again.

## 3.3 "API accepted" is not "delivered"

> When Microsoft answers **API accepted**, it has queued the email for delivery. That is all Microsoft says when it
> sends. The site learns about a failure when a bounce report arrives in the i2g@ Inbox. Once the site has read the
> Inbox well past a send without a report, the email shows **No bounce received**: likely delivered, not proof. It
> shows "Delivered" only with **Message Trace**, an optional feature that is off until IT grants it a permission.

| Shown | Meaning |
|---|---|
| **API accepted** | Microsoft accepted the email for delivery. Not proof that it arrived. |
| **API failed** | Microsoft refused it, or could not be reached. Nothing was sent. |
| **API outcome unknown** | The answer was lost. The email may have been sent, so it is not retried automatically. |
| **Not sent** | The site stopped it before contacting Microsoft (settings, mailbox scope or delivery limits). |
| **Delivery status unknown** | Accepted, and nothing more is known yet: no bounce report, and the site has not read the Inbox far enough past the send. Normal for the first two days after a send. |
| **No bounce received** | The site read the i2g@ Inbox for two days past the send and found no bounce report for it. It most likely arrived, but this is not proof. |
| **Delivered (message trace)** | Only with Message Trace on: Microsoft says it handed the email to the recipient's mail server. That server can still file it as spam. |
| **Quarantined** / **Filtered as spam** | Only with Message Trace on: Microsoft kept the email from the inbox. Tell the web team if many emails show it. |
| **Delivery failure confirmed** | A bounce report (or, with Message Trace, Microsoft's trace) says delivery failed. |
| **Delivery delayed** | A report says the receiving server is still trying. Not a failure yet. |

Right after a blast every email shows **API accepted** and **Delivery status unknown**. Bounce reports arrive over
the next minutes, and some take a day or two; matched ones change the email to **Delivery failure confirmed** or
**Delivery delayed**. About two days later the others change to **No bounce received**. Some receiving servers drop
mail or file it as spam without sending any report, so a missing report is not proof of delivery either, and a late
report still changes the email to **Delivery failure confirmed**.

The campaign's own recipient list shows **Sent** for an email Microsoft accepted.

## 3.4 The Email Monitoring dashboard

Open **Broadcast Delivery → Delivery Operations**: it opens **Email Monitoring**, the one page about email
delivery. Pick a **Range** and **Apply**. (**Delivery monitoring** on a sent campaign opens the same figures for that
one campaign.) Its tabs:

- **Overview:** the **Bounce processing** card (3.5) and the **Delivery status** card below it (3.5); one row of
  key figures (emails sent, API accepted, API failed, the API success rate, confirmed failed emails, emails
  retried, no bounce received, delivered (message trace), quarantined or spam) with the current send rate under it;
  the recipient and API-attempt counts; charts; the most common failure and bounce reasons; and **Broadcast
  campaigns**, one row per campaign with its emails, API accepted, failed / not sent, outcome unknown, confirmed
  failures, failure rate, delivered (trace), quarantined or spam, and retries.
- **Email log:** every email the site sent, with search (an address, for example) and filters. Click one to see its
  full history. It starts on the last 7 days: widen the **Range** for older emails.
- **Bounce reports:** one row per failed recipient in each report, with its category (what went wrong) and match.

The note at the top of every page except **Amazon SES** gives the date of the oldest email on record. Monitoring
began in November 2026, and emails are kept for 180 days, so anything older is not there.

Two more tabs: **Bounced addresses** (3.7) and **Amazon SES**. **Amazon SES** is the old **Delivery Dashboard**
page (its old address opens this tab). It shows Amazon's own figures for mail sent through Amazon SES, one of the
providers **Email Sending Method** can choose (the site never switches to it by itself): attempts, deliveries and
errors by type, with a daily chart (**Range**: 7 days to 12 months), and Amazon's suppression list, the addresses
Amazon refuses to send to, with a search and **Export the rows shown**. These numbers come from Amazon, not from the
site's own record, so they do not match the Overview. Its own note at the top says where its figures come from;
while Microsoft Graph sends the site's mail, a second note says so.

### Bounce reports

Each row has a **category**, read from the codes in the report. Under it, in grey, are the broad classification
(hard, soft, rejected, delayed, unknown) and what the category means. **What the categories mean** on the page lists
them all.

| Category | Usual cause | What to do |
|---|---|---|
| **Address does not exist** | The address, or its domain, does not exist. | Correct the member's address, or mark it undeliverable (3.7). |
| **Mailbox disabled** | The recipient's account or mailbox was explicitly closed or switched off. | Look for another address for the person, or mark it undeliverable (3.7). |
| **Mailbox full** | The person's mailbox is full. | Leave the address eligible and try again after the person frees space. Act only if it keeps happening. |
| **Temporary failure** | A connection timeout or refusal, a DNS problem, a server that said "try again later", a delivery that expired after Microsoft's retries, a message too large, a mailbox set to a "0 KB" size limit, or a mailbox getting too much mail at once (Gmail). | Keep the address eligible: the next blast can try again after the receiving service is fixed. Act only if the same address keeps failing. |
| **Spam or reputation rejection** | A spam filter, a block list, our sending reputation, or a check on our sender (SPF, DKIM, DMARC). | **About our sending, not the contact.** Do not change the member. Tell the web team, with the code and reason. |
| **Relay denied** | The receiving server would not accept our message by this route. | **About our sending (the route or authorisation), not the contact.** Do not change the member. Tell the web team. |
| **Recipient policy rejection** | The receiving server's own rules (for example a group that only takes mail from inside the organisation). | Do not change the member. If it matters, ask the person by another channel to allow mail from i2g@ucmerced.edu. |
| **Delayed (still retrying)** | The receiving side is still retrying. | Nothing. |
| **Unknown failure** | A report without a specific code or a recognisable reason (for example a bare "554 delivery error"). | Read the reason and diagnostic in the row. It is never treated as proof the address is bad. If a category looks wrong, tell the web team the code and the text. |

The match column says how the report was tied to an email: **Exact: original Message-ID** (the report quotes our
message's ID), **Inferred: recipient, subject and time** (the only email to that recipient with that subject in the
five days before the report), or **Not matched**. Unmatched reports are usually about mail someone sent from
Outlook, mail sent before monitoring began, or a case the site will not guess. Anyone can send a fake bounce report,
so treat an unmatched report with care.

Campaigns stop sending to an address when a permanent Graph report matches the original message and its failed final
recipient, or when SES records a permanent bounce or complaint. A forwarded failure or inferred match is evidence
to review. Staff control contact and subscription changes.

For the first review, use the category to choose the next step:

| Group | Categories | Staff action |
|---|---|---|
| **Permanent address problem** | Address or domain does not exist; mailbox explicitly disabled | Confirmed permanent evidence already holds campaigns. Verify the address and review any replacement before changing a member. |
| **Our sending problem** | Relay denied; spam or reputation rejection | Keep the contact address. Give the web team the code and reason so they can correct the route, sender checks or content. Once corrected, review a different configured sending provider for a one-address draft. |
| **Receiving service problem** | Timeout, other temporary failure, 0 KB mailbox limit, mailbox full | Keep the address eligible. After the receiving side is fixed, prepare a one-address draft to retry; review repeated failures over time. |
| **Automatic reply** | Left-the-organisation or vacation automatic reply | A vacation reply needs no bounce action. Open a left-the-organisation notice for manual review before changing any address. |

The Email Monitoring page identifies the problem and suggests an action; it does not resend a failed message or
change the sender automatically.

**In Outlook, leave "Undeliverable" messages in the i2g@ Inbox** until they have been read (bounce scans run every
10 minutes and read only the Inbox). Do not create Outlook rules that move them.

## 3.5 Bounce processing

The **Bounce processing** card at the top of the Overview shows whether bounce reports are being read. Its
controls act on bounce processing only.

| Status | Meaning |
|---|---|
| **Running** | Scans succeed. |
| **Waiting for the first scan** | Just switched on; the first scan has not run yet. |
| **Paused** | Someone clicked **Pause**. |
| **No recent successful scan** | Scans stopped succeeding: tell the web team (the background worker may be down). |
| **Last scan failed** | The card shows the error: tell the web team. |
| **Switched off** | Bounce processing is turned off in the site's configuration: tell the web team. |
| **Not active** | The mailbox is not set up for reading; the card shows the reason. |

The card also shows the mailbox, the last scan, the last successful scan, the **Checkpoint** (how far the reading
has got), the next scan, the interval (every 10 minutes), and what the last scan found.

- **Scan now** asks the background worker to scan for bounce reports within a minute instead of waiting for the
  next scan. It is greyed out while processing is paused or not active.
- **Pause** stops bounce scans; **Resume** starts them again from the checkpoint, so reports that arrived meanwhile
  (and are still in the Inbox) are read then. Pausing does not affect sending, and it stops nothing else that reads
  the i2g@ Inbox: Outlook, the admin's inbox page (3.8) and the helpdesk carry on.

The helpdesk reads the same Inbox with its own scan, every 2 minutes (every 30 seconds while it catches up), and
has its own controls on the **Intake: reading the Inbox** card at the top of **Helpdesk → Settings** (needs the
Helpdesk section):

- **Scan now**, and **Pause intake** / **Resume intake**. While paused, the helpdesk neither reads the Inbox nor
  imports mail; resuming continues from its checkpoint, so mail that arrived meanwhile (and is still in the Inbox)
  becomes tickets then.
- Under **Read older mail again**: **Rescan since** and **First-scan lookback (hours)**, which work like the ones
  for bounce reports (3.6). Messages the helpdesk already has are skipped, so no ticket is made twice.

The two never change each other: **Pause**, **Rescan since** and the lookback on the Bounce processing card act on
bounce processing only, and the intake card's controls act on the helpdesk only. To stop both from reading the Inbox,
pause both. The Bounce processing card then also lists the helpdesk's intake, for example "Helpdesk intake, every 2
min (paused)", with a link to its card.

### The Delivery status card

Below the Bounce processing card, the **Delivery status** card shows:

- **Message Trace**: **Off** (the normal state today, with the steps IT and InfoSec must take first), **Waiting
  for permission**, **Waiting for the first sync**, **Running**, **Throttled by Microsoft** or **Last sync failed**.
  While it is on, **Sync delivery status now** asks for a sync at once (the background worker runs it within a
  minute, unless Microsoft asked to wait).
- **Permission check**: the latest result of **Check permissions**, for example "Message Trace not granted (checked
  Nov 18, 14:05)". **Check permissions** asks Microsoft which permissions the site's key has. It sends no email and
  changes nothing; you can run it again after 30 seconds.
- **No-bounce inference**: **active** (with the send times it covers) or **waiting for scan coverage** (normal for two
  days after the bounce processing starts).

Nothing on this card changes how emails are sent.

## 3.6 Read older mail again

The first scan looks back only 72 hours, so bounce reports that arrived earlier (for example after a blast sent
before Email Monitoring was deployed) were never read. On the **Bounce processing** card, open **Read older mail
again**:

- **Rescan since:** pick a date and time (Pacific time) and click **Rescan since**. The next scan, or **Scan now**,
  reads the Inbox again from that moment. Reports already recorded are skipped, so nothing is counted twice. It is
  refused, with the reason, when the time is in the future, more than 90 days ago, or not earlier than the current
  checkpoint, and while a scan is running (try again a minute later). If processing is paused, the rescan waits until
  it is resumed. Mail that was deleted or moved out of the Inbox cannot be read again.
- **First-scan lookback (hours):** how far back the very first scan of a mailbox reads (1 to 2,160 hours; empty
  means the default of 72). It has no effect once the mailbox has a checkpoint; use **Rescan since** instead.

Both change bounce processing only; the helpdesk has its own (3.5). Both changes are recorded in the admin log
(**Site Settings → Admin Log**, for staff who have that section).

## 3.7 Bounced addresses

The **Bounced addresses** page in Email Monitoring lists every address that has bounced, one row per address,
with what you may do about it. It also lists addresses whose automatic reply to our mail said the person **left the
organisation** (or retired or changed address). Verify any new contact details with the member or organisation.
Staff actions that change an address, account or subscription have a confirmation and an audit record. A trusted
permanent report or signed SES complaint or permanent bounce can reopen a dismissed address and stop campaign
delivery while staff review it.

### The list

- Tabs **Open**, **Dismissed**, **Resolved** and **All**; filters for type, category, role, member, suppressed,
  evidence, suggestion, campaign and date; a search on the address or member name; **Export these rows (.xlsx)**.
- Each row shows the counts by category, the first and last bounce, the latest category and what it means, the last
  reason, the member (with Active, Inactive
  or Staff), the address's role (**Primary**, **Secondary**, **Other**, **Unlinked contact**, **Not a contact** or
  **Ambiguous**), its flags, the campaigns, and a suggestion.
- **Suggestions** are text only and are never applied:

| Suggestion | Why |
|---|---|
| **Unsubscribe: they reported us as spam** | A spam complaint. |
| **Mark undeliverable or replace the address** | Recipient-bound Graph evidence or a signed SES permanent event identifying an invalid address. |
| **Replace the address (the mailbox is disabled), or mark it undeliverable** | A recipient-bound Graph report that the mailbox is disabled. |
| **SES has stopped delivery** | Check the SES suppression, subscription and diagnostic. A provider hold alone does not establish that a person has left. |
| **Review the evidence** | The Graph cause is unknown, older permanent history lacks recipient proof, or SES has no classified receiving cause. Verify before changing the address. |
| **Review the rejected message size, content or attachment** | SES rejected what was sent. Correct the message before considering another campaign. |
| **Our sending side: relay denied…** | Relay refusals and none of the above: check our sending route or authorisation, then use an alternate configured sender to retry. |
| **Our sending side: spam or reputation rejection…** | Spam or reputation rejections and none of the above: check our reputation, sender checks or content, then use an alternate configured sender to retry. |
| **Repeated temporary failures: check the receiving service, then retry this address** | Three or more Graph temporary or full-mailbox failures or confirmed SES temporary receiving failures, with at least seven days between the address's first and last report. A relay or reputation rejection takes priority so staff can check the sending service first. |
| **Their server's policy refused the message, not the address: no action** | Policy rejections and none of the above. |
| **May have left: an automatic reply says so. Check the notice, then replace the address or mark it undeliverable** | An automatic reply to our mail said the person left the organisation, retired or changed address (and none of the first three rows applies). |

A single temporary failure, such as a connection timeout, never suggests marking an address undeliverable. A row
whose reports are all unmatched says "unmatched reports only: check them first" beside a suggestion about the
address itself.

**Retry one address.** Open the address and choose **Prepare one-address draft** beside the original completed
campaign. The address must belong to the same active member who received the original send, with exactly one
verified and subscribed contact. The original recipient log must support a retry. A delivered or uncertain send,
an ambiguous match, an unresolved permanent hold or a complaint blocks the workflow.

- **Receiving problems.** After a receiving limit, full mailbox or temporary service fault is fixed, use matching
  Graph evidence or a signed SES event identifying a temporary receiving problem. A delay means the provider is
  still trying. SES message-size, attachment and content rejections require a content review.
- **Sender problems.** For a Graph spam or relay rejection, have the web team correct the route or reputation
  problem, then review a **different configured sending provider**. Changing the display name or From address on
  the same service is insufficient. If the original provider cannot be established, the draft cannot be created.
- **Repeat requests.** Preparing a draft sends nothing. It locks the recipient, provider and From identity to the
  reviewed values; staff still review the content and confirm the send. Reopening the workflow uses the existing
  retry. Its submitted record and recipient history are protected from deletion.

**Left-the-organisation notices.** When someone's automatic reply to one of our emails says they no longer work
there, the address shows **left the organisation 1** in its counts. Open the address to see when it came, the
name, email address or phone number the notice suggests as a contact, flagged for **manual review**, and, if you
hold the Helpdesk app, a link to the notice itself. Phone hints support US ten-digit / `+1` formats only and are
shown normalized as `+1`; international numbers are ignored. These details come from the notice's text and are not
verified. The hints disappear from details, the replacement form, the filter and exports 90 days after processing,
or sooner if the source is deleted. The notice count and dates remain. Ordinary vacations and lunch breaks are
ignored. A retirement notice with a routine weekend-hours footer still goes to review. Read the notice, then use
**Replace email** or **Mark undeliverable** yourself if needed. The Replace email page shows the named address as a reminder, but you
type the new address: confirm it with the member or their organisation first, since anyone can write such a notice.

### Actions

Open an address (or use a row's **Actions** menu). Each action shows a confirmation page first.

| Action | What it does | Undo | Needs |
|---|---|---|---|
| **Dismiss** | Removes the address from the open list; nothing else changes. | **Reopen** | Mail |
| **Suppress address** | For an address that belongs to no member: every campaign skips it. | **Clear suppression** | Mail |
| **Mark undeliverable** | Every campaign skips this member's address. Sign-in codes, tickets and notifications still go. | **Clear suppression** | Mail + Members |
| **Unsubscribe this address** | Turns off newsletters for this address only. | Re-subscribe on the member page | Mail + Members |
| **Use another address as primary** | A verified address you pick becomes the primary. | Make the old address primary again once it is verified | Mail + Members |
| **Replace email** | Adds the new address to the member, then marks the old one undeliverable or deletes it. Sends nothing. | Partly | Mail + Members |
| **Delete this email address** | Removes the address. You type the address to confirm. | No | Mail + Members |
| **Deactivate account** | The member can no longer sign in; their registrations and history stay. | Activate on the Members page | Mail + Members |
| **Delete account** | Deletes the member and everything that belongs to them, including registrations and check-ins. You type their primary address. Prefer **Deactivate**. | No | I2G Master only |

Changes to a staff or superuser account need the I2G Master. An address that is a member's only address, or their
last verified way to sign in, cannot be deleted.

**Bulk:** tick rows (up to 500) and choose **Dismiss**, **Reopen**, **Suppress address**, **Mark undeliverable**,
**Clear suppression** or **Unsubscribe this address**. The next page lists every address with "will change" or the
reason it is skipped. Changes to addresses and accounts are made one at a time.

### Effect on blasts

Every campaign audience skips a staff-suppressed address, a confirmed permanent Graph failure, and an SES
permanent bounce or complaint. An older ambiguous Graph hard count permits ordinary campaigns and requires
review before a one-address retry. After checking a recovered address, use **Clear suppression** with a note
explaining the verification. A later confirmed permanent report holds the address again. This action cannot lift
an SES restriction or resubscribe a contact. The previews and the
confirmation page say "N recipients skipped: undeliverable". An email already queued for that address is not sent:
the campaign's **Email Log** shows it as **Failed** ("Not sent: this address is suppressed for bulk mail"), and it
counts towards **Partially sent**. Sign-in codes, tickets and notifications still reach the address, in case the
person fixes their mailbox.

### A routine after each blast

1. Wait a day for the reports to come in.
2. Open **Bounced addresses** on the **Open** tab and filter by suggestion.
3. **Address does not exist** or **Mailbox disabled**: open the member, look for a better address, then
   **Replace email**, **Use another address as primary**, or **Mark undeliverable**. **May have left**: read the
   notice first (it names who to contact or their new address), then do the same. Do not deactivate the account
   for a bad address, and do not untick **Verified** to stop mail: it stops sign-in, not mail (chapter 2, "A
   bounced address: what to do").
4. Complaints: **Unsubscribe this address**.
5. **Temporary failures** (timeouts, 0 KB limits, full mailboxes): keep the address eligible. After the receiving
   service is fixed, use **Prepare one-address draft** beside retryable evidence from that exact campaign; after
   repeated failures, check the cause with the recipient before trying again. **Unknown** failures also remain
   eligible for normal mail, but inspect their evidence: unknown-only evidence cannot create a retry draft.
6. **Relay denied** and **spam or reputation rejections**: keep the contact address. Give the code and reason to the
   web team, then use **Prepare one-address draft** after the sending problem is fixed. **Policy rejections**: leave
   them.
7. **Dismiss** what needs nothing, with a short reason.

## 3.8 Replies to a blast

Replies arrive in the i2g@ucmerced.edu Inbox. Read them in Outlook or on **Broadcast Delivery → Gmail Inbox**:
despite its name, that page shows the i2g@ucmerced.edu mailbox when Microsoft Graph is set up to read it, and it
warns about suspicious messages. Replies often quote the original email, including the
person's own sign-in link: do not forward replies outside the I2G team. A helpdesk that turns each message into a
ticket is being built (chapter 4). It hides automatic replies, newsletters and other automated mail, but a person's
answer to our email stays in its queue even when they sent it from a sales or marketing tool (such as Salesforce) that
adds newsletter-style headers. An answer sent to a whole mailing list is the exception for now: it is filed with the
automated mail, marked **reply to our mail**, so check those too.

## 3.9 Troubleshooting

| Problem | What to check |
|---|---|
| **Send Campaign** is missing | The campaign has not been saved yet (save it first), or it has already been sent (use **Duplicate campaign**). |
| "No recipients found for this audience" (a grey **No Recipients Found** button on the preview) | The audience is empty: check the event, ticket or member selection and **Send to**. |
| The confirmation word is not accepted | On the send confirmation, type the campaign's name exactly as shown (**Confirm & Send** stays grey until it matches). Everywhere else, type the word the page shows. |
| Some recipients are **Paused by delivery limits** | A delivery limit (the hourly or daily allowance, or a pause from Microsoft) held them back while the web server itself was sending. Run **Resume paused recipients** later and tell the web team. |
| A person says they never got the blast | Open the campaign's **Email Log** tab. Not listed: they were not in the audience (unsubscribed, inactive, or a different address). **Retry scheduled** or **Paused**: it has not gone yet. **Sent**: search their address in **Email Monitoring → Email log**, with a **Range** that covers the send date. **API accepted** with **Delivery status unknown** or **No bounce received** means Microsoft accepted it and no bounce came back: ask them to check spam and other folders. **Quarantined** or **Filtered as spam**: tell the web team. |
| A sign-in link "does not work" | It expired, was already used, or was revoked, or the account is inactive. The person can sign in with a code instead. |
| Many **Rejected** reports | Tell the web team: it is usually about our sending, not the addresses. |
| The **Bounce processing** card is not **Running** | **Paused** (someone paused it) and **Waiting for the first scan** (just switched on) can be normal. Anything else: tell the web team. |
| The **Delivery status** card says Message Trace is **Off** or **Waiting for permission** | Normal until IT grants the Message Trace permission. Emails still show **No bounce received** after two days. |

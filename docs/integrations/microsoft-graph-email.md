# Microsoft Graph Email (Outlook / Exchange Online)

Operator runbook for sending the application's email through Microsoft Graph: the Microsoft-side setup,
the Django admin settings, how the provider behaves, its limits, and what each error means.

## What it is and when to use it

The Microsoft Graph provider sends mail from an Outlook / Exchange Online mailbox. The backend signs in
as an Entra application (OAuth 2.0 client-credentials flow, `Mail.Send` application permission, no
signed-in user) and calls Graph `sendMail` once per message. The request body is the complete MIME
message the app builds for every provider, base64-encoded, so every header (`List-Unsubscribe`,
`In-Reply-To`, `References`), inline image, and attachment (such as the ticket calendar file) is sent
as built. Graph's JSON message format would accept only custom headers that start with `x-`.

It is the third choice of the **Provider** setting:

| | AWS SES | SMTP | Microsoft Graph |
|---|---|---|---|
| Credentials | Shared AWS IAM key (`AWSCredentialConfig`) | Host, port, optional username and password (`SMTPProviderConfig`) | Entra tenant ID, client ID, client secret (`MicrosoftGraphProviderConfig`) |
| Transport | SES API, raw MIME | SMTP submission | HTTPS `sendMail`, base64 MIME |
| Message ID recorded | SES message ID | MIME `Message-ID` | MIME `Message-ID` |
| Delivery events | Yes, through the [SNS webhook](ses-event-tracking.md) | No | No |
| Provider limits | SES account quotas | The SMTP server's | Per mailbox: about 30 messages per minute, 10,000 recipients per day |

- **One provider for all app email.** Login codes, ticket emails, admin invitations, inbox replies,
  campaigns, and the test email all use the active provider. There is no per-message routing and no
  fallback: when Graph fails, the message is not re-sent through SES or SMTP.
- **Use it** when mail must leave from an Exchange Online mailbox (user or shared) and the site should
  authenticate with an app registration instead of a mailbox password.
- **Do not rely on it for bulk mail.** One mailbox carries all of the site's email within the
  [limits](#limits) below, and Microsoft recommends Azure Communication Services Email for bulk mail.

## Prerequisites and Entra setup

You need:

- An account that can register applications and grant admin consent in the Entra tenant.
- An Exchange Online administrator for the PowerShell step, with the `ExchangeOnlineManagement` module.
- A sender mailbox in Exchange Online, user or shared. Graph cannot send as an on-premises mailbox or as
  an address that has no mailbox (`404`, see the [error reference](#error-reference)).
- An admin account with access to the **Mail** app, to enter the settings.

### 1. Register the application

In the Microsoft Entra admin center open **App registrations** and choose **New registration**.

- Name: for example `I2G website mail`.
- Supported account types: **Accounts in this organizational directory only** (single tenant).
- Leave the redirect URI empty.

On the Overview page copy **Application (client) ID** and **Directory (tenant) ID**.

### 2. Add the Mail.Send application permission

**API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions** →
`Mail.Send` → **Add permissions**, then **Grant admin consent**. Delegated permissions do not apply:
no user is signed in.

### 3. Create a client secret

**Certificates & secrets** → **New client secret**. Choose an expiry (24 months at most) and copy the
**Value** immediately; it is shown once. The **Secret ID** beside it is not the secret.

Put the expiry date in a calendar with a reminder well before it. When the secret expires, every email
the site sends fails, login codes included, until a new secret is saved
([Rotate the client secret](#rotate-the-client-secret)).

### 4. Limit the app to the sender mailbox

`Mail.Send` as an application permission lets the app send as **any** mailbox in the tenant. Until this
step is finished, the site's credentials can do exactly that. Restrict them to the sender mailbox with
*RBAC for Applications* in Exchange Online. In Exchange Online PowerShell:

```powershell
Connect-ExchangeOnline

# Make the Entra app known to Exchange. ObjectId is the Object ID of the enterprise application
# (Entra > Enterprise applications), not of the app registration.
New-ServicePrincipal -AppId <client-id> -ObjectId <enterprise-app-object-id> -DisplayName "I2G website mail"

# The mailbox the app may use.
New-ManagementScope -Name "I2G sender mailbox" -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'sender@example.edu'"

# Grant Mail.Send inside that scope only.
New-ManagementRoleAssignment -App <service-principal> -Role "Application Mail.Send" -CustomResourceScope "I2G sender mailbox"

# Check: InScope must be True for the sender mailbox and False for any other mailbox.
Test-ServicePrincipalAuthorization -Identity <service-principal> -Resource sender@example.edu
```

`<service-principal>` is the identity Exchange shows for the app (`Get-ServicePrincipal`). The syntax
follows Microsoft's article listed under [Sources](#sources), which is the reference if a cmdlet reports
different parameters.

Once the check passes, **remove the tenant-wide permission**. With the consent from step 2 still in
place the app can send as any mailbox and the scope has no effect. In Entra open the app's **API
permissions**, remove `Mail.Send` (or revoke the admin consent), and leave the Exchange role assignment
as the only grant.

Exchange can take 30 minutes to 2 hours to apply the change, and sends fail with `403` until it has.
Make the change at a quiet time and run **Send Test Email** afterwards.

## Configure in Django admin

1. Open **Mail → Notification Delivery**: in the sidebar choose **Delivery Operations** (group
   **Broadcast Delivery**), switch to the **Notification Delivery** tab (`/admin/mail/settings/`), and
   select **Edit Notification Delivery**.
2. Under **Email Sender**, set **Provider** to **Microsoft Graph**, tick **Active**, and set **From Name**
   and **From Email**. The **Microsoft Graph Provider** panel opens below the other panels.
3. Fill in the **Microsoft Graph Provider** panel (table below) and tick its **Active** box.
4. Select **Save Notification Delivery**.
5. Back on the Notification Delivery page select **Send Test Email**, enter an address you can open, and
   send.

| Field | Value |
|-------|-------|
| **Config Name** | Label for this configuration (default `Default`). |
| **Active** | Tick it. Only one Microsoft Graph configuration can be active; activating one deactivates the others. |
| **Tenant ID** | Directory (tenant) ID as a GUID, or a verified domain such as `contoso.onmicrosoft.com`. `common`, `organizations`, and `consumers` are rejected. |
| **Client ID** | Application (client) ID of the Entra app registration (a GUID). |
| **Client Secret** | The secret **value**, not the secret ID. Required while the configuration is active. The saved value is never displayed again; leave the field blank when editing to keep it, except after changing **Tenant ID** or **Client ID**: a different application needs its own secret, so the form asks for it again. |
| **Sender Mailbox** | Optional. Email address, user principal name, or object ID (GUID) of the Exchange Online mailbox that sends. Blank means the **From Email** address. |
| **Messages per Minute** | 1 to 30, default 24. Exchange Online allows 30 messages per minute per mailbox, so keep this below that limit. See [Campaign pacing](#campaign-pacing). |

- **From Email** must be the sender mailbox or an address that mailbox may send as; otherwise Graph
  answers `403` (`ErrorSendAsDenied`).
- With the Graph panel's **Active** box unticked, saving stops with "An active Microsoft Graph
  configuration is required before activation." under **Provider**. A missing **Tenant ID** or **Client
  ID** is reported on the field, and an active configuration also needs a **Client Secret**.
- Choosing AWS SES or SMTP later hides the Graph panel and keeps the saved Graph settings, secret
  included. The AWS panel on the same page is always saved and is still used for SMS.
- The model is also at `/admin/core/microsoftgraphproviderconfig/`, deliberately not in the sidebar.
  An active configuration cannot be deleted there.
- A successful test reports `Test email sent to <address> via Microsoft Graph (config: <name>).` That
  means Graph accepted the message (HTTP 202), not that it was delivered. A failure reports
  `Failed to send test email: <message>`; the messages are explained in the
  [error reference](#error-reference).

### Rotate the client secret

1. In Entra create a new client secret. The old one keeps working.
2. Paste the new **Value** into **Client Secret**, save, and send a test email.
3. Delete the old secret in Entra.

The new secret applies to the next send in every process; no restart is needed.

### Check the stored configuration

```bash
cd src && python manage.py verify_service_configs --strict
```

The command prints `MicrosoftGraphProviderConfig: OK (<name>)` when the configuration is complete
(active, with a well-formed tenant ID and client ID, a client secret, and a well-formed sender mailbox if one is set) and `MISSING` when Graph is the selected provider
but is not. It prints nothing about Graph when another provider is selected and no Graph configuration
exists. With `--strict`, a selected but incomplete Graph provider makes the command fail. It reads stored
settings only and does not contact Microsoft; use **Send Test Email** to prove the credentials.

## How it behaves

- **Request flow.** The backend requests an access token from
  `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token` (client-credentials grant, scope
  `https://graph.microsoft.com/.default`), then sends
  `POST https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail` with `Content-Type: text/plain` and
  the base64 MIME as the body. Only those two hosts are used, over TLS 1.2 or later, without following
  redirects or using proxy environment variables, with a 30-second timeout per request. The backend and
  worker containers need outbound HTTPS to both.
- **Message ID.** `sendMail` answers `202 Accepted` with no body and no message ID, so the app records
  the `Message-ID` header it generated as the provider message ID in the Email Log (`RecipientLog`,
  provider `graph`), as it does for SMTP. Its domain part is the **From Email** domain
  (`<...@g.ucmerced.edu>`), never the server's internal host name.
- **202 means queued, not delivered.** A later failure, such as an unknown recipient or a rejection by
  the recipient's server, comes back as a non-delivery report in the sender mailbox's Inbox. The app
  does not read that mailbox and receives no delivery events, so Email Log rows stay `sent`; they never
  become `delivered`, `bounced`, or `complained`, as with SMTP. Someone should watch the sender mailbox
  for non-delivery reports. The Delivery Dashboard charts SES CloudWatch metrics only and says so in a
  notice while another provider is active.
- **Sent Items.** Every message is saved in the sender mailbox's Sent Items folder, and MIME mode cannot
  turn that off. A campaign leaves one copy per recipient. Set a retention policy for the folder (the
  period is a records-policy decision) and watch the mailbox size: a full mailbox makes Graph answer
  `507`, and sending stops until space is freed.
- **No Bcc.** The app builds no Bcc header and Graph has no separate envelope, so a Bcc recipient would
  silently receive nothing. Such a message is refused as a permanent error. No current feature sends
  Bcc.
- **Tokens.** Access tokens are kept only in each process's memory (never in the database, the cache,
  or on disk), keyed by tenant, client ID, and a hash of the secret, and renewed shortly before they
  expire. Each process therefore requests its own token about once an hour. A `401` or `403` from Graph
  drops the cached token, so consent or role changes made after it was issued apply to the next send.
- **No retry inside the provider.** One request is made per message. Retrying is left to the caller
  (see the [error reference](#error-reference)), and an uncertain outcome is never retried
  automatically.
- **Secrets.** The client secret is stored in the database with the other service credentials, not in
  environment variables, and the admin forms never display it. The model is on the safe-ORM denylist,
  so the `i2g-admin` CLI and the AI assistant cannot read or change it. The provider's error messages
  and log lines carry no secret, token, or response body.

| Concern | Location |
|---------|----------|
| Sending, token cache, HTTPS, error mapping | `src/apps/core/services/email/graph/` (`provider.py`, `auth.py`, `transport.py`, `errors.py`) |
| Provider selection | `src/apps/core/services/email/registry.py` |
| Settings model | `src/apps/core/models/base/service_credentials/microsoft_graph.py` |
| Notification Delivery forms | `src/apps/mail/admin/settings/forms.py` |

## Limits

Microsoft's limits for one sender mailbox, as published on Microsoft Learn (see [Sources](#sources)):

| Limit | Value | Applies to |
|-------|-------|------------|
| Messages per minute | About 30 | Each mailbox |
| Recipients per day | 10,000 | Each mailbox |
| Recipients per message | 500 | Each message |
| Concurrent requests | 4 | Each app and mailbox |
| Requests per 10 minutes | 10,000 | Each app and mailbox |

All app email shares one mailbox, so a campaign draws on the same allowance as login codes, tickets,
invitations, and test emails. Login-code emails are capped per destination but not in total (see
[Send verification](../deployment/send-verification.md)), so a burst of code requests for many
different addresses can use the same allowance. The provider does not meter requests itself. Campaigns
are paced as described under [Campaign pacing](#campaign-pacing); ticket and notification emails are paced
only while background jobs are enabled; login codes, invitations, replies, and a member's own ticket resend
are never paced. When Graph throttles a request it answers `429` or
`503` and the app treats that as a transient failure; watch the sender mailbox Inbox for non-delivery
reports too when volume is high.

### Campaign pacing

While Graph is the active provider the app sends at a **Graph rate**: the lower of **Campaign Send Rate**
(whole emails per second; `0` means no cap) and **Messages per Minute** divided by 60. Setting **Campaign
Send Rate** to `0` does not unpace Graph; it falls back to **Messages per Minute**. At the default of 24
messages per minute the rate is 0.4 emails per second, and 1,000 recipients take about 42 minutes. The
Notification Delivery page shows the rate as `24 emails/min`.

- **Where it applies.** Campaigns, sent by the background worker or by the in-process sender. Both take
  their turn from one schedule per provider, shared by every worker, web process, and campaign. Ticket
  emails sent at registration and notification emails (subscription confirmations, security notices) are
  paced too, but only while background jobs are enabled, because only then are they queued. When a Graph
  campaign is queued, its recipients become due one pace apart, so ticket and notification emails queued
  meanwhile go out between them instead of waiting for the whole campaign.
- **Where it does not.** Emails sent straight from a request are not paced: login codes, admin invitations
  (including the multi-select **Resend selected pending invitations** action, which has no 20-email cap),
  inbox replies, the test email, the **Send ticket email now** button and **Send ticket email to
  attendee** checkbox, and a member's own ticket resend from their account page. With background jobs
  disabled (the default), registration ticket emails and notification emails are sent this way too, and
  are not retried when Graph throttles them. All of these share the mailbox allowance with campaigns, so
  keep **Messages per Minute** below 30.
- **`Retry-After`.** When Graph or the identity platform answers `429`/`503` with a `Retry-After` value,
  the background worker schedules that email's next attempt no sooner than that (capped at one hour, and
  never sooner than its normal backoff). Other queued emails are not held back and keep their paced slots,
  so a long throttle can cost several of them a retry too. Without the worker, a throttled recipient is
  recorded as `failed`.
- **Confirmation page.** Before a campaign is sent, the confirmation page shows the rate, the expected
  duration, and the 10,000-recipients-per-day cap. It warns when the campaign has more recipients than
  that cap, and, when background jobs are disabled, that the web server sends the campaign itself and a
  deploy or restart during that time stops it and leaves the remaining recipients unsent. It does not
  block the send.
- **Bulk ticket actions.** Sending ticket emails from one request (**Send All Tickets** on the Event
  Registrations list, which opens *Send Ticket Emails to All Registrants*, and the multi-select **Resend
  ticket email** action) is refused above 20 registrations while Graph is active, because those sends
  are not paced. Select fewer registrations or switch the email
  provider.
- **Not enforced.** The 10,000-recipients-per-day cap is only warned about. Nothing counts the mailbox's
  daily total, and non-delivery reports for messages over it arrive in the sender mailbox Inbox.

## Error reference

Every failure is classified so callers know whether sending again is safe:

- **Transient**: nothing was sent, or Microsoft asked for a later retry. Sending again is safe.
- **Permanent**: sending the same message again will fail the same way. Fix the cause first.
- **Uncertain**: Graph may have accepted the message, so sending again could duplicate it. It is never
  retried automatically. The sender mailbox's Sent Items folder is the best evidence: a copy there
  means Exchange accepted the message. Wait and check again before sending it again.

How a campaign records these depends on how it runs. With the background worker enabled
(`BACKGROUND_JOBS_ENABLED`, see [Environments](../deployment/environments.md)) a recipient becomes
`retry` (transient, retried automatically with growing delays), `failed` (permanent), or `uncertain`
(review it, then use the admin retry action). Without the worker, the in-process sender makes one
attempt per recipient and records every failure as `failed`, keeping the message. One-off sends such as
the test email show the error and can be repeated.

The **Message recorded** columns below are the provider's message. **Send Test Email** shows it, the
in-process sender stores it on the Email Log, queued ticket emails store it on the registration, and with
the worker it is the job's **Last error** (Admin → Background Jobs). With the worker, the Email Log and the
send-status page show only `Temporary delivery failure; retry scheduled.`, `Delivery failed before the
provider confirmed acceptance.`, or `Provider call outcome is uncertain; review before retrying.`; ticket
emails sent from the admin record `Ticket email delivery provider failed.`

Messages are generic by design. The parenthesised code is Graph's `error.code` (or Microsoft's OAuth
error and AADSTS number); for a rejected `sendMail`, Graph's request ID goes to the backend
log only (see [Troubleshooting](#troubleshooting-checklist)). Token-request failures log no Microsoft
correlation ID; quote the AADSTS number and the time instead.

### sendMail responses

| Result | Class | Message recorded | Cause and action |
|--------|-------|------------------|------------------|
| `202` | Success | none | Accepted for sending; not a delivery confirmation. |
| `401` | Transient | `Microsoft Graph rejected the access token; it will be refreshed.` | The cached token is dropped and the retry fetches a new one. If it repeats, check **Tenant ID**, **Client ID**, and the secret. |
| `403` | Permanent | `Microsoft Graph rejected the request (ErrorAccessDenied).` or `(ErrorSendAsDenied)` | The app may not send as this mailbox or address: the consent was removed before the RBAC assignment applied, the mailbox is outside the management scope, the change has not propagated yet (30 minutes to 2 hours), or **From Email** is not the mailbox or an address it may send as. The cached token is dropped, so the next send uses a new one that carries any consent granted since. |
| `404` | Permanent | `Microsoft Graph rejected the request (MailboxNotEnabledForRESTAPI).` or `(ResourceNotFound)` | **Sender Mailbox** (or **From Email**, when blank) is not an Exchange Online mailbox, or is misspelled. Use the mailbox's primary address. |
| `400` | Permanent | `Microsoft Graph rejected the request (<code>).` | Graph refused the request or the MIME content, for example an invalid recipient. The code names the problem. |
| `413` | Permanent | `Microsoft Graph rejected the request (<code>).` | The message is too large, usually attachments. The request-size limit for MIME `sendMail` is not documented in the pages under [Sources](#sources). |
| Other `4xx` | Permanent | `Microsoft Graph rejected the request (<code>).` | Look the code up on Microsoft's Graph errors page. |
| `408`, `429`, `503` | Transient | `Microsoft Graph temporarily rejected the request.` | Throttled or briefly unavailable. The `Retry-After` value (capped at 3,600 seconds) delays the background worker's next attempt; see [Campaign pacing](#campaign-pacing). If `429` recurs, lower **Messages per Minute**. |
| `507` | Permanent | `The sender mailbox is full (HTTP 507); free space in the mailbox.` | The mailbox is full, typically Sent Items. Delete old items and set a retention policy. |
| `500`, `502`, `504`, other `5xx`, any other status | Uncertain | `Microsoft Graph returned HTTP <status>; delivery could not be confirmed (<code>).` | A gateway error can follow acceptance. Check Sent Items before resending. |
| Cannot connect, or the TLS handshake fails, before the request is sent | Transient | `Microsoft Graph could not be reached before sending.` | Outbound HTTPS to `graph.microsoft.com` is blocked or the network is down. Nothing was sent. |
| Certificate verification fails | Permanent | `TLS verification of Microsoft Graph failed.` | TLS interception, or an outdated CA bundle in the container. Nothing was sent. |
| Timeout or reset after the request began | Uncertain | `Microsoft Graph response was lost after the request began.` | As for `5xx`. |
| An unexpected local error after the request was handed over | Uncertain | `Microsoft Graph request outcome could not be confirmed.` | Logged at ERROR as `Unexpected <ExceptionType> while sending through Microsoft Graph` (the type only). Check Sent Items before resending. |

### Access token requests

A token request sends no mail, so these failures are always certain: nothing was sent.

| Result | Class | Message recorded | Cause and action |
|--------|-------|------------------|------------------|
| `invalid_client`, `AADSTS7000215` | Permanent | `Microsoft rejected the Graph credentials (invalid_client AADSTS7000215).` | Wrong client secret. A common cause is the secret ID pasted instead of the value. |
| `invalid_client`, `AADSTS7000222` | Permanent | `Microsoft rejected the Graph credentials (invalid_client AADSTS7000222).` | The client secret has expired. [Rotate it](#rotate-the-client-secret). |
| `unauthorized_client`, `AADSTS700016` | Permanent | `Microsoft rejected the Graph credentials (unauthorized_client AADSTS700016).` | No app with this **Client ID** exists in this tenant. Check **Client ID** and **Tenant ID**. |
| Any other rejection (an unknown tenant, `invalid_scope`, other `4xx`) | Permanent | `Microsoft rejected the Graph credentials (<error> AADSTS<number>).` | Look the AADSTS number up in Microsoft's error-code reference. |
| `408`, `429`, `5xx` | Transient | `Microsoft identity platform is temporarily unavailable.` | Retried later by the background worker (`Retry-After`, when sent, delays that retry); without the worker the send fails once. |
| Cannot connect | Transient | `Microsoft identity platform could not be reached.` | Outbound HTTPS to `login.microsoftonline.com` is blocked or the network is down. |
| No answer, or reset | Transient | `Microsoft identity platform did not answer.` | Safe to repeat. |
| `200` with an unreadable body | Transient | `Microsoft identity platform returned an unreadable response.` | Safe to repeat. |
| Certificate verification fails | Permanent | `TLS verification of the Microsoft identity platform failed.` | TLS interception, or an outdated CA bundle in the container. |

### Refused before any request is made

| Situation | Class | Message recorded | Cause and action |
|-----------|-------|------------------|------------------|
| A Bcc recipient is present | Permanent | `Microsoft Graph does not support Bcc recipients.` | Send separate messages instead. |
| The MIME message cannot be built | Permanent | `The email could not be composed for Microsoft Graph.` | Fix the message. Composition errors raised by the shared MIME builder keep their own message, for example `Email has no recipients.` |
| **Sender Mailbox** is blank and **From Email** is not a valid address | Permanent | `Microsoft Graph configuration is invalid.` | The sender mailbox falls back to **From Email**, which must be an address or object ID. |
| No active, complete, well-formed Graph configuration | Permanent | `Active Microsoft Graph provider configuration is missing or invalid.` | Tick **Active** in the Graph panel and fill in **Tenant ID**, **Client ID**, and **Client Secret**. A row saved outside the admin with a malformed tenant ID, client ID, or sender mailbox counts as not configured; re-save it in the admin. |
| No active email configuration | Permanent | `No active email service configuration exists.` | Tick **Active** under **Email Sender**. |

## Troubleshooting checklist

1. **Test email fails with "Microsoft rejected the Graph credentials".** Check **Tenant ID** and
   **Client ID** against the app's Overview page, and that **Client Secret** is the secret value of a
   secret that has not expired (**Certificates & secrets**). Re-enter the value; a blank field keeps
   the old one.
2. **Test email fails with `(ErrorAccessDenied)` or `(ErrorSendAsDenied)` (HTTP 403).** Run `Test-ServicePrincipalAuthorization` for the sender mailbox
   (`InScope` must be True). After a new assignment, or after removing the tenant-wide consent, wait up
   to 2 hours. Check that the management scope filter matches the mailbox, and that **From Email** is
   the sender mailbox or an address it may send as.
3. **Test email fails with `(MailboxNotEnabledForRESTAPI)` or `(ResourceNotFound)` (HTTP 404).** Check the **Sender Mailbox** spelling, and confirm in the Exchange
   admin center that it is an Exchange Online mailbox rather than an on-premises one.
4. **"Test email sent", but nothing arrives.** HTTP 202 only means queued. Look in the sender mailbox:
   Sent Items should hold a copy, and the Inbox may hold a non-delivery report with the reason. Check
   the recipient's junk folder.
5. **All email suddenly fails.** The client secret may have expired (`AADSTS7000222`) or the mailbox may
   be full (`507`). Check **Certificates & secrets** in Entra and the mailbox size.
6. **Frequent `429` or "temporarily rejected".** Lower **Messages per Minute**, stop other tools that
   send as the same mailbox, and see [Limits](#limits).
7. **Campaign recipients marked `uncertain`, or `failed` after a Graph error.** Read the job's **Last
   error** (Admin → Background Jobs) and the [error reference](#error-reference); check Sent Items before
   sending again.
8. **Confirm the stored settings.** Run `python manage.py verify_service_configs --strict`.
9. **Ask Microsoft for help.** Each rejected `sendMail` writes one backend log line at WARNING level,
   `Microsoft Graph sendMail was not accepted: status=<status> code=<code> request_id=<id>` (CloudWatch
   Logs in production). Quote the request ID and the time. If a message has no code in parentheses,
   `status=<status>` in that line tells the cases apart. An unexpected error after a send began writes
   `Unexpected <ExceptionType> while sending through Microsoft Graph` at ERROR level instead.

First live check after a new setup or a credential change:

1. Send a test email to an external mailbox you can open. Confirm it arrives, shows the configured
   **From Name** and **From Email**, and leaves a copy in the sender mailbox's Sent Items.
2. Send a small campaign to yourself. In the received message's headers confirm `List-Unsubscribe` and
   `List-Unsubscribe-Post`, and that the `Message-ID` matches the provider message ID in the Email Log.
3. Send yourself a ticket email. Confirm the inline barcode image displays and the calendar file is
   attached, and that a subject or name with accented characters displays correctly. Confirm the received
   message shows a sent date (the app does not write a `Date` header; Exchange is expected to add one).
4. In a non-production environment, save a deliberately wrong secret and confirm the test email reports
   `Microsoft rejected the Graph credentials (invalid_client AADSTS7000215)`. Restore the real secret.
5. Confirm the small campaign completed without `429` responses.

## Sources

- [`sendMail` API reference](https://learn.microsoft.com/en-us/graph/api/user-sendmail): MIME format, the `202` response, and the Sent Items copy.
- [Things to know about sending mail](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail)
- [Microsoft Graph throttling limits](https://learn.microsoft.com/en-us/graph/throttling-limits): concurrent requests and requests per 10 minutes.
- [Microsoft Graph error responses](https://learn.microsoft.com/en-us/graph/errors)
- [RBAC for Applications in Exchange Online](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac): scoping an app to specific mailboxes.
- [OAuth 2.0 client credentials flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)
- [Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits): messages per minute, recipients per day and per message.
- [Microsoft Entra authentication and authorization error codes](https://learn.microsoft.com/en-us/entra/identity-platform/reference-error-codes): the AADSTS numbers.

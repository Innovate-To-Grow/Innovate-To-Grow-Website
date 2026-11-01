# Microsoft Graph Email (Outlook / Exchange Online)

Operator runbook for sending the application's email, and reading the I2G inbox, through Microsoft Graph:
the Microsoft-side setup, the Django admin settings, the mailbox scope, access validation, monitoring,
credential rotation, retention, emergency revocation, the limits, and what each error means.

## What it is and when to use it

The Microsoft Graph provider sends mail from an Outlook / Exchange Online mailbox and, with read
permission, shows that mailbox in the admin inbox. The backend signs in as an Entra application (OAuth 2.0
client-credentials flow with a **certificate**, `Mail.Send` and `Mail.Read` application permissions, no
signed-in user) and calls Graph `sendMail` once per message. The request body is usually the complete
MIME message the app builds for every provider, base64-encoded, so every header (`List-Unsubscribe`,
`In-Reply-To`, `References`), inline image, and attachment (such as the ticket calendar file) is sent
as built. Graph always files a copy of a MIME `sendMail` in the sender mailbox's Sent Items, so mail that
carries a credential (sign-in codes and links, admin invitations, tickets) is sent in Graph's JSON format
with `saveToSentItems: false` instead; see [Sent Items](#sent-items-and-credential-mail).

It is the third choice of the **Provider** setting:

| | AWS SES | SMTP | Microsoft Graph |
|---|---|---|---|
| Credentials | Shared AWS IAM key in Secrets Manager, referenced by `AWSCredentialConfig` | Host, port, optional username and password (`SMTPProviderConfig`) | Entra tenant ID and client ID, an installed certificate whose private key is kept in the credential store (AWS Secrets Manager in production), and a mailbox scope (`MicrosoftGraphProviderConfig`, `MicrosoftGraphCertificate`) |
| Transport | SES API, raw MIME | SMTP submission | HTTPS `sendMail`: base64 MIME, or JSON for credential mail |
| Message ID recorded | SES message ID | MIME `Message-ID` | MIME `Message-ID` (none for a JSON send) |
| Delivery events | Yes, through the [SNS webhook](ses-event-tracking.md) | No | No |
| Provider limits | SES account quotas | The SMTP server's | Per mailbox: about 30 messages per minute, 10,000 recipients per day |

- **One provider for all app email.** Login codes, ticket emails, admin invitations, inbox replies,
  campaigns, and the test email all use the active provider. There is no per-message routing and no
  fallback: when Graph fails, the message is not re-sent through SES or SMTP.
- **Use it** when mail must leave from an Exchange Online mailbox (user or shared) and the site should
  authenticate with an app registration instead of a mailbox password.
- **UC Merced approval.** InfoSec approved application-level `Mail.Send` and `Mail.Read` for the dedicated
  `i2g@ucmerced.edu` mailbox only, with certificate authentication, no further Graph permissions without a
  new InfoSec review, and proof that access is denied for an unrelated mailbox
  ([Validate the access restriction](#validate-the-access-restriction)). This runbook covers each condition.

### Two layers restrict the mailbox

1. **Exchange Online (Microsoft enforces it).** RBAC for Applications grants `Mail.Send` and `Mail.Read`
   inside a management scope that contains only the I2G mailbox ([step 4](#4-limit-the-app-to-the-i2g-mailbox)).
2. **The site (defense in depth).** Each Graph configuration has a **mailbox scope**: a list of mailboxes,
   each with a permission level (*Send only*, *Read only*, or *Send and read*). The site refuses, before
   contacting Microsoft, any send as or read of a mailbox that is not listed with that permission. Nothing
   is hard-coded: the scope is data in Django admin and must match the Exchange role assignments.
- **Do not rely on it for bulk mail.** One mailbox carries all of the site's email within the
  [limits](#limits) below, and Microsoft recommends Azure Communication Services Email for bulk mail.

## Prerequisites and Entra setup

You need:

- An account that can register applications in the Entra tenant (UC Merced: Cloud Systems).
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

### 2. Do not grant tenant-wide Graph permissions

Do **not** add `Mail.Send` or `Mail.Read` under **API permissions** with admin consent. An Entra
application permission is tenant-wide, and Exchange adds it to any scoped grant, so the restriction in
step 4 would have no effect. The only grants are the Exchange role assignments in step 4. If they were
added earlier, remove them (or revoke the admin consent) once step 4 is in place.

### 3. Create and upload a certificate

The app proves its identity with a certificate (Microsoft's `private_key_jwt`): it signs a short-lived
assertion with the private key, and Entra checks it against the uploaded certificate. The private key
never leaves the server, so nothing reusable crosses the network. The site supports no client secrets.

Create an RSA key (2048 bits or more) and a certificate. A self-signed certificate is fine; Entra only
checks that the key matches. Do this on a trusted workstation, not on a shared server:

```bash
openssl req -x509 -newkey rsa:3072 -sha256 -days 365 -nodes \
  -subj "/CN=I2G website mail" -keyout i2g-graph.key -out i2g-graph.crt
```

- Upload `i2g-graph.crt` under **Certificates & secrets** → **Certificates** → **Upload certificate**.
  Note the expiry date; a reminder is also built in ([Monitoring](#monitoring)).
- `i2g-graph.key` is the private key. It is installed once (next section); the site keeps it in the
  credential store, never in the database. Store no other copy, and delete the local file once it is
  installed.
- The private key may also be a PKCS#1 PEM, an encrypted PEM with its passphrase, or part of a
  `.p12`/`.pfx` file with its password (what macOS Keychain exports); the certificate may also be a DER
  `.cer` file.

### 4. Limit the app to the I2G mailbox

Grant `Mail.Send` and `Mail.Read` with *RBAC for Applications* in Exchange Online, scoped to the I2G
mailbox only. In Exchange Online PowerShell:

```powershell
Connect-ExchangeOnline

# Make the Entra app known to Exchange. ObjectId is the Object ID of the enterprise application
# (Entra > Enterprise applications), not of the app registration.
New-ServicePrincipal -AppId <client-id> -ObjectId <enterprise-app-object-id> -DisplayName "I2G website mail"

# The only mailbox the app may use.
New-ManagementScope -Name "I2G mailbox" -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'i2g@ucmerced.edu'"

# The two approved permissions, inside that scope only.
New-ManagementRoleAssignment -App <client-id> -Role "Application Mail.Send" -CustomResourceScope "I2G mailbox"
New-ManagementRoleAssignment -App <client-id> -Role "Application Mail.Read" -CustomResourceScope "I2G mailbox"

# Check: InScope must be True for i2g@ucmerced.edu and False for any other mailbox.
Test-ServicePrincipalAuthorization -Identity <client-id> -Resource i2g@ucmerced.edu
Test-ServicePrincipalAuthorization -Identity <client-id> -Resource <unrelated-test-mailbox>
```

The syntax follows Microsoft's article listed under [Sources](#sources), which is the reference if a
cmdlet reports different parameters. `Test-ServicePrincipalAuthorization` ignores permissions granted in
Entra, which is why step 2 must leave none there; [Validate the access
restriction](#validate-the-access-restriction) checks the real effect.

Exchange can take 30 minutes to 2 hours to apply a change, and requests fail with `403` until it has.

## Configure in Django admin

Credentials and the mailbox scope live in the database like the other service credentials (AWS, SMTP),
never in code or environment variables. Configure the Graph config first, then select Graph as the
provider.

1. Open `/admin/core/microsoftgraphproviderconfig/` (deliberately not in the sidebar; the Notification
   Delivery page links to it) and add a configuration:

   | Field | Value |
   |-------|-------|
   | **Config Name** | Label for this configuration (default `Default`). |
   | **Active** | Tick it. Only one Graph configuration can be active; activating one deactivates the others. |
   | **Tenant ID** | Directory (tenant) ID as a GUID, or a verified domain such as `contoso.onmicrosoft.com`. `common`, `organizations`, and `consumers` are rejected. |
   | **Client ID** | Application (client) ID of the Entra app registration (a GUID). |
   | **Certificate** (panel above the form) | The installed certificate: SHA-1 thumbprint (as Entra lists it under **Certificates & secrets**), SHA-256 fingerprint, subject, serial, validity with an expiry badge (amber `GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS`, default 60, and red `GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS`, default 14, days before expiry), the key store and version, and the Entra check result, plus the previous certificate kept for rollback. The form itself has no certificate, key or secret input. |
   | **Sender Mailbox** | `i2g@ucmerced.edu`. Blank means the **From Email** address. The admin inbox reads this mailbox too. |
   | **Messages per Minute** | 1 to 30, default 24. Exchange Online allows 30 messages per minute per mailbox. See [Campaign pacing](#campaign-pacing). |
   | **Mailbox scope** (inline rows) | One row: mailbox `i2g@ucmerced.edu`, permission **Send and read (Mail.Send + Mail.Read)**. |
   | **Access Check Deny Mailbox** | Superusers only. The unrelated test mailbox OIT / InfoSec designated for the denial test ([Validate the access restriction](#validate-the-access-restriction)). |
   | **InfoSec Exception Reference** | Superusers only, and only after InfoSec has approved in writing Graph permissions beyond `Mail.Send` and `Mail.Read`: the reference of that review. Leave it blank otherwise. |
   | **Access check** (panel above the form) | The latest access check: verdict, date, certificate, deny mailbox and the token's roles, with a link to the recorded result, and whether it is go-live evidence. Superusers get **Run access check**. |

   **Tenant ID** and **Client ID** are read-only while a certificate is installed: a certificate is
   tested for one tenant and app. To move to another app, set up a standby configuration for it, install
   its certificate there and then activate it, or remove the certificates first.

   A superuser installs the certificate with **Install certificate** on the configuration's page. The
   page takes the `.p12`/`.pfx` file with its password, or the certificate (PEM, base64, or the DER
   `.cer` file) and the private key (PEM PKCS#8 or PKCS#1, optionally encrypted, with its passphrase),
   pasted or uploaded (each at most `GRAPH_CERTIFICATE_MAX_INPUT_BYTES`). An optional **Expected SHA-1
   thumbprint** (case, colons and spaces ignored) stops the install when the certificate differs. It is a
   separate page, not the configuration form: nothing entered is kept in the session or cache, the key and
   password inputs are never shown again, and error reports hide them. The panel also offers **Roll back
   to previous**, **Remove (emergency)** (type `REMOVE` and give a reason; it can switch email to AWS SES
   in the same step) and **Download .cer** (the public certificate, for OIT). Staff with the **Core** app
   see the panel and can download the `.cer`, but only a superuser can change the certificate.

   Installing a certificate (`apps.core.services.email.graph.credential.lifecycle`) checks, in memory,
   that the key is RSA of at least `GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS` (2048) bits and belongs to the
   certificate, that the input holds exactly one certificate and the certificate input no private key,
   and that the certificate is valid now. It then requests one token from Entra with the key: a wrong
   tenant, unknown or disabled app refuses the install before anything is stored, and on the active
   configuration only a certificate Entra accepts is installed. The key is then written to the credential
   store, and the new version is pinned as the current certificate; the replaced one becomes previous.
   Every message is fixed text and never contains key material. The certificate alone (no key) re-issues
   the installed key when its public key matches.
2. Set **Access Check Deny Mailbox** and run the [access validation](#validate-the-access-restriction)
   (**Run access check**). In production, Notification Delivery refuses Microsoft Graph until a run with
   the current certificate matches the approval.
3. Open **Mail → Notification Delivery**: in the sidebar choose **Delivery Operations** (group
   **Broadcast Delivery**), switch to the **Notification Delivery** tab (`/admin/mail/settings/`), and
   select **Edit Notification Delivery**.
4. Under **Email Sender**, set **Provider** to **Microsoft Graph**, tick **Active**, set **From Name** and
   **From Email** (`i2g@ucmerced.edu`), and select **Save Notification Delivery**. The Graph panel shows the
   configuration from step 1 read-only (with the certificate's SHA-1 thumbprint and expiry, the mailbox
   scope and the latest access check); this page cannot change it. Staff with the **Core** app get a link
   to the configuration page.
5. Send a test email.

- The **From Email** and the sending mailbox must both be in the scope with send permission; otherwise
  saving stops under **Provider** with "An active Microsoft Graph configuration whose mailbox scope lets
  the sender mailbox and the From address send is required before activation."
- Choosing AWS SES or SMTP later hides the Graph panel and keeps the saved Graph settings. The AWS panel on
  the same page is always saved and is still used for SMS.
- An active configuration cannot be deleted. Deleting an inactive one deletes its scope rows.
- While Notification Delivery sends through Graph, the configuration page refuses a save that would stop
  email: deactivating the sending configuration, activating a standby that cannot send, or a mailbox scope
  or sender mailbox that no longer lets the sender and the **From Email** send. Select another provider
  first.
- A successful test reports `Test email sent to <address> via Microsoft Graph (config: <name>).` That
  means Graph accepted the message (HTTP 202), not that it was delivered. A failure reports
  `Failed to send test email: <message>`; the messages are explained in the
  [error reference](#error-reference).

### Mailbox scope and permission levels

| Permission level | The site may | Exchange role assignment it needs |
|------------------|--------------|-----------------------------------|
| Send only (Mail.Send) | send as the mailbox | `Application Mail.Send` |
| Read only (Mail.Read) | list and open messages in its Inbox and Sent Items | `Application Mail.Read` |
| Send and read | both | both |

- An empty scope allows nothing: the configuration counts as not configured and every Graph request is
  refused.
- The site checks the sending mailbox and the **From Email** for send, and the inbox mailbox for read,
  before each request. A refusal is a permanent error naming the mailbox (see
  [Refused before any request is made](#refused-before-any-request-is-made)).
- Mailboxes are compared case-insensitively, and two rows for one mailbox are refused. Use the same form
  in the scope as in **Sender Mailbox**: an object ID (GUID) in one place and an address in the other do
  not match.
- Staff with the **Core** app can edit the scope, like the rest of the configuration.
- Adding a mailbox here does not grant anything at Microsoft; the Exchange role assignment must also
  exist. Adding a mailbox or permission beyond the approval needs a new InfoSec review.
- The scope model is on the safe-ORM denylist, so the `i2g-admin` CLI and the AI assistant cannot read
  or change it.

### Validate the access restriction

The access check asks Microsoft directly, bypassing the site's own scope check, what the Entra app may do
and compares it with the InfoSec approval (`Mail.Send` and `Mail.Read` for the I2G mailbox). A
superuser runs it with **Run access check** on the Graph configuration's page (production has no ECS
Exec), or from a shell:

```bash
cd src && python manage.py verify_graph_access
```

Before the first run a superuser sets **Access Check Deny Mailbox** on the configuration: an existing
mailbox outside the scope, designated by OIT / InfoSec for the denial test (a plain email address, not
another name of a scoped mailbox). `--deny-mailbox <address>` tries another one, but only runs against
the designated mailbox count as go-live evidence. Each run requests a fresh token with the current
certificate and records one **Microsoft Graph Access Check** row (Core app, read-only): the certificate,
the deny mailbox, every probe line, the token's roles and the verdict. No token, response body or
message content is stored.

| Check | Mailbox | Expected |
|-------|---------|----------|
| `token` | | issued for the current certificate |
| `roles` | | the token's `roles` claim within `GRAPH_APPROVED_APPLICATION_ROLES` (default `Mail.Send`, `Mail.Read`) |
| `folder`, `list`, `value` | each scoped mailbox with read permission | `200`: the Inbox, the newest message with its preview (`$top=1&$select=id,bodyPreview`), and the first `GRAPH_ACCESS_CHECK_MIME_MAX_BYTES` (default 4096) of its raw MIME, which is discarded |
| `send` | each scoped mailbox with send permission, listed by address | `202`: a MIME probe email to itself (a copy stays in its Sent Items) |
| `read+` | each scoped mailbox with send permission only | for the record: a `200` is a WARN, because an access policy limits mailboxes, not permissions, so only the site's scope stops reading it |
| `folder`, `list` | the deny mailbox | `403` |
| `send` | as the deny mailbox, addressed to the I2G mailbox | `403` |
| `sendas` | the I2G mailbox, with the deny mailbox as From | `403` (`ErrorSendAsDenied`): the I2G mailbox holds no Send As or Send on Behalf right on it |

How to read the result:

- The two sends that must be refused are JSON `sendMail` with `saveToSentItems: false`, addressed to the
  I2G mailbox. If Exchange wrongly accepts one, it files no Sent Items copy and reaches only the I2G
  mailbox, and the line reads `ACCESS WAS GRANTED` with a note that a probe email was sent.
- The token's `roles` are decoded without verifying the token (Microsoft supports decoding only for
  debugging). Any role beyond the approval, such as `Mail.ReadWrite`, is a FAIL, unless a superuser has
  recorded **InfoSec Exception Reference** (the reference of InfoSec's written review; the site never
  fills it in), which turns it into a WARN that names the reference. No roles is a WARN: RBAC for
  Applications grants never appear in the token. Unreadable roles are INCONCLUSIVE.
- A `403` for the deny mailbox counts only when the same kind of request succeeded for a scoped mailbox
  in the same run. Otherwise it is INCONCLUSIVE, because an app that may do nothing at all also gets `403`.
- A `403` whose message starts with `Access to OData is disabled` is noted as an Exchange Application
  Access Policy refusal (an EWS access policy gives the same message). A deny mailbox that does not
  exist fails with a `404` note.
- Each line shows the HTTP status, the Graph error code and Microsoft's request ID, so it can be matched
  with Entra sign-in and Exchange logs.
- A skipped check (`--no-send`, no mailbox with read or send permission, a sender listed only by object
  ID) is SKIP. A run with any SKIP or INCONCLUSIVE line ends with `NOT A COMPLETE VALIDATION`.

The summary line reads, for example, `Mailbox restriction: HOLDS · Granted roles: BEYOND the approval
(Mail.ReadWrite) · Verdict: DOES NOT MATCH THE APPROVAL`. The command exits non-zero unless the verdict
is **Matches the approval**: the restriction holds, nothing failed or was skipped, and the roles are
within the approval or covered by a recorded exception. Run it after setup, after any Exchange or Entra
change, and after rotation. Microsoft notes that access policy changes can take more than an hour to
apply, so wait after OIT changes anything. The recorded rows are the validation evidence for InfoSec.

**Go-live gate.** Where `GRAPH_REQUIRE_ACCESS_EVIDENCE` is on (production; off locally and in tests),
Mail → Notification Delivery can switch email to Microsoft Graph only when the latest access check run
with the current certificate matched the approval, used the designated deny mailbox, and is at most
`GRAPH_ACCESS_EVIDENCE_MAX_AGE_DAYS` (default 30) days old. A role beyond today's approval still needs an
exception reference at the time of the switch, so clearing the reference withdraws the evidence. The
gate guards the switch only: editing a config that already sends through Graph is not blocked. The
certificate panel shows the latest result and whether the evidence is present.

### Rotate the certificate

Entra accepts several certificates on one app, so rotation has no downtime:

1. Create a new key and certificate ([step 3](#3-create-and-upload-a-certificate)) and upload the
   certificate to the app in Entra. The old one keeps working.
2. Install the new certificate and private key. Check that the SHA-1 thumbprint and expiry shown in the
   admin match Entra. The replaced certificate is kept as previous, so a rollback (after a fresh Entra
   token test with the previous key) is possible until the next install.
3. Run the access check (**Run access check** or `verify_graph_access`) and send a test email. Evidence
   recorded for the old certificate does not count for the new one.
4. Remove the old certificate from the app in Entra, and destroy any remaining copy of the old key.

The new credential applies to the next request in every process; no restart is needed. Rotate before
the `GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS` threshold (default 14 days before expiry; reminders start at
`GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS`, default 60, see [Monitoring](#monitoring)), and immediately if
the key may have been exposed ([Emergency revocation](#emergency-revocation)).

### Check the stored configuration

```bash
cd src && python manage.py verify_service_configs --strict
```

The command prints `MicrosoftGraphProviderConfig: OK (<name>)` when Graph can send (active, a well-formed
tenant ID and client ID, a current certificate that is valid now, a mailbox scope, and the sending
mailbox and **From Email** in that scope with send permission) and `MISSING` when Graph is the selected
provider but cannot. It also reports a missing scope, a missing certificate or one that is not valid yet,
and certificate expiry: a warning from `GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS` (default 60) days before,
and a problem from `GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS` (default 14) days before or once expired.
Problems are failures while Graph is the selected provider and warnings otherwise. Dates are shown in the
site's time zone, as in the admin. It prints nothing about Graph when another provider is selected and no
Graph configuration exists. With `--strict`, a failure makes the command exit non-zero, so a scheduled
`--strict` run fails two weeks before the certificate stops email. It reads stored settings only and does
not contact Microsoft; the access check and **Send Test Email** prove the credentials.

## How it behaves

- **Request flow.** The backend requests an access token from
  `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token` (client-credentials grant, scope
  `https://graph.microsoft.com/.default`). With a certificate it sends a client assertion: a JWT signed
  with the private key (`PS256`, header `x5t#S256` = the certificate's SHA-256 thumbprint, valid for 5
  minutes, a fresh `jti` each time), never the key itself. It then sends
  `POST https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail` with `Content-Type: text/plain` and
  the base64 MIME as the body, or with `Content-Type: application/json` for credential mail. Only those
  two hosts are used, over TLS 1.2 or later, without following redirects or using proxy environment
  variables, with a 30-second timeout per request. The backend and worker containers need outbound HTTPS
  to both.
- **Only five kinds of request.** The transport (`transport.py`, `ALLOWED_REQUESTS`) refuses, before
  opening a connection, every request except the token request, `POST …/users/{mailbox}/sendMail`,
  `GET …/mailFolders/{inbox|sentitems}/messages`, `GET …/mailFolders/inbox` (the access-check probe) and
  `GET …/messages/{id}/$value`. No code path can create a draft, reply, move, flag, mark read or delete
  mail, whatever permissions the Entra app holds. OIT reported configuring `Mail.ReadWrite` rather than the
  approved `Mail.Read` (not verified on our side); the allowlist keeps the site itself from using the extra
  permission, but it does not limit someone who obtains the key or a token. A refused request is the
  permanent error `The site does not make this Microsoft Graph request.`
- **Message ID.** `sendMail` answers `202 Accepted` with no body and no message ID, so the app records
  the `Message-ID` header it generated as the provider message ID in the Email Log (`RecipientLog`,
  provider `graph`), as it does for SMTP. Its domain part is the **From Email** domain
  (`<...@g.ucmerced.edu>`), never the server's internal host name. A JSON send sets no `Message-ID`
  (Exchange assigns one) and reports none; no current JSON-sent message is recorded in the Email Log.
- **202 means queued, not delivered.** A later failure, such as an unknown recipient or a rejection by
  the recipient's server, comes back as a non-delivery report in the sender mailbox's Inbox. The app
  shows that Inbox to admins (see [Admin inbox](#admin-inbox)) but does not parse it, and receives no
  delivery events, so Email Log rows stay `sent`; they never become `delivered`, `bounced`, or
  `complained`, as with SMTP. Someone should watch the sender mailbox
  for non-delivery reports. The Delivery Dashboard charts SES CloudWatch metrics only and says so in a
  notice while another provider is active.
- **Sent Items.** A MIME `sendMail` is always saved in the sender mailbox's Sent Items folder; credential
  mail is sent as JSON and leaves no copy. See [Sent Items and credential mail](#sent-items-and-credential-mail).
- **Bcc.** The MIME builder writes no Bcc header and Graph has no separate envelope for MIME, so a MIME
  message with a Bcc recipient is refused as a permanent error rather than silently not delivered to it. The
  JSON form has its own Bcc list and delivers it. No current feature sends Bcc.
- **Tokens.** Access tokens are kept only in each process's memory (never in the database, the cache,
  or on disk), keyed by tenant, client ID, the pinned key version and the certificate thumbprint, and renewed shortly before
  they expire. Each process therefore requests its own token about once an hour. A `401` or `403` from Graph
  drops the cached token, so consent or role changes made after it was issued apply to the next send.
- **No retry inside the provider.** One request is made per message. Retrying is left to the caller
  (see the [error reference](#error-reference)), and an uncertain outcome is never retried
  automatically.
- **Protecting the private key.** The private key is never stored in the database, code, images, task
  definitions, or environment variables. It is kept in the credential store
  (`apps.core.services.credential_store`): the AWS Secrets Manager secret
  `itg/backend/microsoft-graph/certificate-key` in production, a 0600 file under the gitignored
  `src/data/` locally, and process memory in tests. The database keeps only the certificate's public data
  and the pinned store version (`MicrosoftGraphCertificate`). On a token-cache miss the pinned version is
  read, checked against the certificate's public key, used to sign one assertion and dropped; no process
  caches the key. Only staff granted the **Core** app can open the configuration, and only a superuser can
  install, roll back or remove a certificate; **Mail → Notification Delivery** shows the configuration
  read-only. Changelist filters on secret-looking field names (`?private_key__regex=…`) are refused with
  `400` on every admin page. The config, its scope and its certificates are on the safe-ORM denylist, so the
  `i2g-admin` CLI and the AI assistant cannot read or change them. Error messages and log lines carry no
  key, token, or response body.

| Concern | Location |
|---------|----------|
| Sending, token cache, HTTPS and its request allowlist, error mapping | `src/apps/core/services/email/graph/` (`provider.py`, `auth.py`, `transport.py`, `errors.py`) |
| JSON `sendMail` body for credential mail | `src/apps/core/services/email/graph/json_message.py` |
| Certificate facts and client assertions | `src/apps/core/services/email/graph/certificate.py` |
| Certificate input, stored key, Entra test, install / rollback / remove | `src/apps/core/services/email/graph/credential/` |
| Mailbox scope enforcement | `src/apps/core/services/email/graph/access.py` |
| Reading the mailbox (`Mail.Read`) | `src/apps/core/services/email/graph/mailbox.py`, `src/apps/mail/services/inbox/graph_backend.py` |
| Sent mail access in the admin inbox | `src/apps/mail/admin/inbox/helpers.py` (`sent_mail_restricted`, `sent_mail_denied`) |
| Access validation (probes, roles, verdict, evidence) | `src/apps/core/services/email/graph/access_check/`, `manage.py verify_graph_access` |
| Recorded access checks and the go-live gate | `src/apps/core/models/base/service_credentials/microsoft_graph_access_check.py`, `EmailServiceConfig.validate_activation` |
| Certificate expiry thresholds (badge, `verify_service_configs`, worker) | `src/apps/core/services/email/graph/credential/expiry.py` |
| Provider selection | `src/apps/core/services/email/registry.py` |
| Settings and scope models | `src/apps/core/models/base/service_credentials/microsoft_graph.py` |
| Installed certificates (public data + key pointer) | `src/apps/core/models/base/service_credentials/microsoft_graph_certificate.py` |
| Certificate pages, certificate panel, Run access check, recorded checks, mailbox scope inline and its guard | `src/apps/core/admin/service_credentials/microsoft_graph*.py` |
| Notification Delivery (selects the provider; Graph read-only) | `src/apps/mail/admin/settings/` |

### Sent Items and credential mail

A MIME `sendMail` is always saved in the sender mailbox's Sent Items folder; only the JSON format can turn
that off (`saveToSentItems: false`). A copy of a sign-in code or link there would let anyone who can read
the folder (mailbox delegates in Outlook, or admin staff in the Sent folder of **Mail → Inbox**) sign in as
the recipient, so a message marked `keep_sent_copy=False` (`apps.core.services.email.EmailMessage`) is sent
as JSON. These are marked:

- **Verification codes**, every purpose (`send_verification_email`: login, admin login, register, password
  reset and change, account deletion, contact and event-registration email checks), with the sign-in links
  they carry: the code or link signs in or authorises an account change.
- **Admin invitations**: the acceptance URL creates a staff account for whoever holds it.
- **Ticket emails**: the ticket code is the check-in credential, and the member's login link signs in.

The JSON form carries the subject, one body (the HTML body when there is one, otherwise the text body), To,
Cc, Bcc, Reply-To, attachments (inline ones keep their Content-ID, so the ticket barcode still displays) and
custom headers whose names start with `x-`. Graph accepts no other custom header in this form, so any other
header is left out and its name logged at WARNING
(`Microsoft Graph JSON sendMail cannot carry these headers, so they were left out: …`); the marked messages
set none.

Everything else stays MIME and keeps a Sent Items copy: campaigns (one copy per recipient; they need
`List-Unsubscribe`), inbox replies, security and subscription notices, the test email and access-check
probes. **Campaigns that use `{{login_link}}` therefore leave live login links in Sent Items** for as long
as each link is valid. Only superusers can open Sent mail in **Mail → Inbox** (see
[Admin inbox](#admin-inbox)); the M365 admins should keep human Full Access to the mailbox to a minimum.
Set a retention policy for the folder (the period is a records-policy decision) and watch the mailbox size:
a full mailbox makes Graph answer `507`, and sending stops until space is freed.

## Admin inbox

When the active Graph configuration grants read permission on its sending mailbox, **Mail → Inbox** reads
that mailbox through Graph instead of Gmail IMAP; otherwise the Gmail import account is used as before.
The page shows the mailbox and `Microsoft Graph` as the source.

- It lists the newest messages of **Inbox** or **Sent Items**
  (`GET /v1.0/users/{mailbox}/mailFolders/{inbox|sentitems}/messages`) and opens a message as its original
  MIME (`GET /v1.0/users/{mailbox}/messages/{id}/$value`), so the scam detector still sees
  `Authentication-Results`, `Reply-To`, and `Return-Path`, and replies keep `In-Reply-To` / `References`.
- **Sent mail is for superusers only.** Sent Items holds what the site sends as MIME, including campaign
  login links, so other staff with the Mail app see no **Sent** tab, a request for the Sent folder shows the
  Inbox instead, and opening or replying to Sent mail answers `403`. A Graph message ID is unique in the
  whole mailbox rather than per folder, so any message whose sender is the sending mailbox or the
  **From Email** counts as Sent mail too, whichever folder the link names (a reply quotes the original, so
  it is refused like opening it). If the inbox backend cannot be resolved, Sent mail stays hidden. The
  Gmail IMAP inbox is unchanged.
- **No AI review of Sent mail.** A message in the medium rule-score band normally gets a second opinion
  from Amazon Bedrock (sender, Reply-To, subject, `Authentication-Results` and the first 4,000 characters of
  the body). Sent mail, by folder or by sender as above, keeps the rule score only and is never sent to
  Bedrock: the site wrote it, and it can hold live codes (a password-reset code scores in the medium band
  because of the word "password"). Inbox mail is still reviewed.
- **Replies.** To and Cc must be plain addresses (`name@example.com`); a quoted local part, a display name,
  a comment or an HTML metacharacter is refused with `Use plain email addresses such as name@example.com in
  To and Cc.` before anything is sent, because the To address is copied from the original sender's From
  header. The confirmation is shown as text, never as HTML.
- The site only reads: opening a message does not mark it read in Outlook, and nothing is moved or deleted
  (see [Only five kinds of request](#how-it-behaves)). Replies are sent through the email provider (Graph
  `sendMail`, MIME, with a Sent Items copy).
- Lists are cached for 5 minutes and opened messages for 30 minutes in the site cache, as with IMAP;
  **Refresh** reloads the list. A message larger than 25 MB is not shown; open it in Outlook.
- Read failures show "Inbox is not available…" and write one WARNING log line,
  `Microsoft Graph mailbox read was refused: status=<status> code=<code> request_id=<id>`.

## Monitoring

| Signal | Where | Action |
|--------|-------|--------|
| `Microsoft Graph sendMail was not accepted: status=… code=… request_id=…` (WARNING) | Backend and worker logs (CloudWatch Logs) | Alert on a burst; see the [error reference](#error-reference). |
| `Microsoft Graph mailbox read was refused: …` (WARNING) | Backend logs | A `403` means the Exchange scope changed; run the access check. |
| `Microsoft rejected the Graph credentials (…)` | Email Log, Background Jobs **Last error**, test email | Certificate or app problem; see [Access token requests](#access-token-requests). |
| `Microsoft Graph certificate expiry warning: <n> days left; …` (WARNING, hourly) | Worker logs, from `GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS` (default 60) days before the active config's certificate expires | Rotate ([Rotate the certificate](#rotate-the-certificate)). |
| Certificate expiry | The panel's expiry badge (amber at the warning, red at `GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS`, default 14); `verify_service_configs --strict` fails from the critical threshold while Graph is selected | Rotate before the critical threshold. |
| Access check | **Microsoft Graph Access Checks** in the admin (Core app); the panel's **Go-live evidence** line | Re-run after any Entra / Exchange change or certificate rotation. |
| Sign-ins of the app | Entra → Enterprise applications → the app → **Sign-in logs** (service principal sign-ins) | Unexpected IPs or failures. |
| Mailbox activity | Microsoft Purview audit log for `i2g@ucmerced.edu` (`Send`, `MailItemsAccessed`), run by the M365 admins | Investigations. |
| Non-delivery reports, mailbox size | The I2G Inbox and Sent Items | Watch for bounces; a full mailbox stops sending (`507`). |

Suggested CloudWatch metric filters: `"Microsoft Graph sendMail was not accepted"`,
`"Microsoft Graph mailbox read was refused"`, and `"Microsoft rejected the Graph credentials"`, each with
an alarm on a count above the normal baseline over 15 minutes, and
`"Microsoft Graph certificate expiry warning"` with an alarm on any match. Running
`verify_service_configs --strict` after each deploy also catches certificate expiry.

## Retention

- **Mailbox.** Every MIME message the site sends stays in Sent Items (one copy per campaign recipient,
  including any `{{login_link}}`); credential mail sent as JSON leaves no copy there. Received mail stays in
  the Inbox. Retention is set by the UC Merced Microsoft 365 records policy for the mailbox, not by the
  site; a short Sent Items period limits how long campaign login links sit there.
- **Site.** The Email Log (`RecipientLog`) and campaign records keep recipients, subjects, status, and the
  `Message-ID`; inbox views are cached for at most 30 minutes; access tokens live only in process memory
  for about an hour. The site stores no copy of received mail.
- **Logs.** Graph log lines carry status, error code, and request ID only, under the CloudWatch Logs
  retention configured for the ECS log groups.
- **Credentials.** A replaced or removed certificate's key version stays in the credential store
  (Secrets Manager cannot delete a single version), but no row pins it, so the site never reads it
  again; it stops working once Entra no longer lists its certificate. Destroy any other copy of the key.

## Emergency revocation

If the private key may be exposed, or the app must stop at once, do the steps in this order. The first two
stop new tokens; the third removes the mailbox permissions themselves.

1. **Entra (Cloud Systems):** remove the certificate from the app (**Certificates & secrets**). No new
   token can be issued with that key.
2. **Entra:** disable the enterprise application (**Properties** → **Enabled for users to sign in** = No),
   or delete it to remove everything at once.
3. **Exchange Online:** remove the role assignments
   (`Get-ManagementRoleAssignment -RoleAssignee <client-id> | Remove-ManagementRoleAssignment`).
4. **Site:** remove the installed certificates (current and previous), which clears the pin so every
   process refuses to sign at its next token request without any store or Entra call; the removal can
   switch **Provider** back to **AWS SES** in the same step when SES is configured. Otherwise set the
   provider on Notification Delivery so email keeps working. The admin inbox falls back to Gmail IMAP.

An access token that was already issued stays valid until it expires (about 60 to 90 minutes), and
Exchange applies role-assignment removals within 30 minutes to 2 hours. Steps 1 and 2 are therefore the
fastest way to stop new access; a token leak (not a key leak) also ends at expiry. After recovery, issue
a new certificate, re-run [Validate the access restriction](#validate-the-access-restriction), and record
the incident.

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
  retried automatically. For a MIME send the sender mailbox's Sent Items folder is the best evidence: a
  copy there means Exchange accepted the message. Wait and check again before sending it again. Credential
  mail (JSON, see [Sent Items and credential mail](#sent-items-and-credential-mail)) leaves no copy, so
  for it ask the recipient or use the Exchange message trace.

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
| `401` | Transient | `Microsoft Graph rejected the access token; it will be refreshed.` | The cached token is dropped and the retry fetches a new one. If it repeats, check **Tenant ID**, **Client ID**, and the installed certificate. |
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
| `invalid_client`, `AADSTS700027` | Permanent | `Microsoft rejected the Graph credentials (invalid_client AADSTS700027).` | The assertion's signature or key is not recognised: the certificate in the admin is not (or no longer) uploaded to this app in Entra. Compare the thumbprint shown in the admin with the one in Entra. |
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
| The sending mailbox or **From Email** is not in the mailbox scope with send permission | Permanent | `Microsoft Graph may not send as <mailbox>: it is not in the configured mailbox scope with that permission.` | Add the mailbox to the scope (and to the Exchange role assignment, after InfoSec review) or fix **Sender Mailbox** / **From Email**. |
| No usable current certificate (none, removed, expired, not valid yet, or tested for another app) | Permanent | `No usable Microsoft Graph certificate is installed.` | Install a certificate; check its validity in the admin. |
| The pinned key cannot be read from the credential store | Transient (throttling, outage, timeout) or Permanent | `The Microsoft Graph private key could not be read: <fixed text> (<AWS error code>)` | Permanent codes such as `AccessDeniedException` or `ResourceNotFoundException` mean the task role or the secret is wrong; reinstall the certificate if its version is gone. |
| The stored key does not match the installed certificate | Permanent | `The Microsoft Graph private key could not be read: The stored private key does not match the installed certificate.` | Reinstall the certificate with its own private key. |
| The certificate private key cannot be used to sign | Permanent | `The Microsoft Graph certificate private key could not be used.` | Reinstall the certificate and private key. |
| A Bcc recipient is present on a MIME message | Permanent | `Microsoft Graph does not support Bcc recipients.` | Send separate messages instead. |
| The MIME or JSON message cannot be built | Permanent | `The email could not be composed for Microsoft Graph.` | Fix the message. Composition errors raised by the builders keep their own message, for example `Email has no recipients.`, `An email recipient address is invalid.` or `An email header is malformed.` |
| A request outside the allowlist | Permanent | `The site does not make this Microsoft Graph request.` | A code defect, or a mailbox value whose encoding is refused (an encoded `.`, `/` or `\`). Nothing was sent. |
| **Sender Mailbox** is blank and **From Email** is not a valid address | Permanent | `Microsoft Graph configuration is invalid.` | The sender mailbox falls back to **From Email**, which must be an address or object ID. |
| No active, complete, well-formed Graph configuration | Permanent | `Active Microsoft Graph provider configuration is missing or invalid.` | Tick **Active**, fill in **Tenant ID** and **Client ID**, install a certificate, and add at least one mailbox scope row. An expired certificate, or a row saved outside the admin with a malformed tenant ID, client ID, or sender mailbox, counts as not configured; fix and re-save it in the admin. |
| No active email configuration | Permanent | `No active email service configuration exists.` | Tick **Active** under **Email Sender**. |

## Troubleshooting checklist

1. **Test email fails with "Microsoft rejected the Graph credentials".** Check **Tenant ID** and
   **Client ID** against the app's Overview page, and that the certificate shown in the admin
   (SHA-1 thumbprint, expiry) is uploaded to that app under **Certificates & secrets**.
2. **Test email fails with `(ErrorAccessDenied)` or `(ErrorSendAsDenied)` (HTTP 403).** Run `Test-ServicePrincipalAuthorization` for the sender mailbox
   (`InScope` must be True). After a new assignment, or after removing the tenant-wide consent, wait up
   to 2 hours. Check that the management scope filter matches the mailbox, and that **From Email** is
   the sender mailbox or an address it may send as.
3. **Test email fails with `(MailboxNotEnabledForRESTAPI)` or `(ResourceNotFound)` (HTTP 404).** Check the **Sender Mailbox** spelling, and confirm in the Exchange
   admin center that it is an Exchange Online mailbox rather than an on-premises one.
4. **"Test email sent", but nothing arrives.** HTTP 202 only means queued. Look in the sender mailbox:
   Sent Items should hold a copy, and the Inbox may hold a non-delivery report with the reason. Check
   the recipient's junk folder.
5. **All email suddenly fails.** The certificate may have expired (the configuration then counts as not
   configured) or been removed in Entra (`AADSTS700027`), or the mailbox may be full (`507`). Check **Certificates & secrets** in Entra,
   `verify_service_configs`, and the mailbox size.
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
2. Request a sign-in code for your own account. Confirm it arrives with the same From and that **no** copy
   is in Sent Items (JSON `sendMail` with `saveToSentItems: false`).
3. Send a small campaign to yourself. In the received message's headers confirm `List-Unsubscribe` and
   `List-Unsubscribe-Post`, and that the `Message-ID` matches the provider message ID in the Email Log.
4. Send yourself a ticket email. Confirm the inline barcode image displays and the calendar file is
   attached, that a subject or name with accented characters displays correctly, and that no copy is in
   Sent Items. Confirm the received
   message shows a sent date (the app does not write a `Date` header; Exchange is expected to add one).
5. In a non-production environment, install a throwaway certificate that is not registered on the app
   on an inactive configuration and confirm its Entra check reads `invalid_client AADSTS700027`.
6. Confirm the small campaign completed without `429` responses.
7. After a credential change, run the access check again: evidence recorded with another certificate does
   not count for the go-live gate.

## Sources

- [`sendMail` API reference](https://learn.microsoft.com/en-us/graph/api/user-sendmail): the JSON and MIME formats, `saveToSentItems`, custom `x-` headers (`internetMessageHeaders`), the `202` response, and the Sent Items copy of a MIME send.
- [Things to know about sending mail](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail)
- [Microsoft Graph throttling limits](https://learn.microsoft.com/en-us/graph/throttling-limits): concurrent requests and requests per 10 minutes.
- [Microsoft Graph error responses](https://learn.microsoft.com/en-us/graph/errors)
- [RBAC for Applications in Exchange Online](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac): scoping an app to specific mailboxes, the `Application Mail.Send` / `Application Mail.Read` roles, and why tenant-wide Entra grants must be removed.
- [Access tokens in the Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens): the `roles` claim, and that apps decode tokens for validation and debugging only.
- [Limit application permissions to specific Exchange Online mailboxes](https://learn.microsoft.com/en-us/graph/auth-limit-mailbox-access): Application Access Policies, and that policy changes can take more than an hour to apply.
- [Microsoft identity platform certificate credentials](https://learn.microsoft.com/en-us/entra/identity-platform/certificate-credentials): the client assertion format (`PS256`, `x5t#S256`, claims).
- [Get MIME content of a message](https://learn.microsoft.com/en-us/graph/outlook-get-mime-message) and [List messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages): the `Mail.Read` calls the admin inbox makes.
- [OAuth 2.0 client credentials flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)
- [Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits): messages per minute, recipients per day and per message.
- [Microsoft Entra authentication and authorization error codes](https://learn.microsoft.com/en-us/entra/identity-platform/reference-error-codes): the AADSTS numbers.

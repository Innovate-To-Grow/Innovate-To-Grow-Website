# Microsoft Graph Email (Outlook / Exchange Online)

Operator runbook for sending the application's email, and reading the I2G inbox, through Microsoft Graph:
the UC Merced status, the Microsoft-side setup, installing the certificate in Django admin, where the private
key is kept, access validation and the go-live gate, rotation, monitoring, retention, emergency revocation,
the limits, and what each error means.

## What it is and when to use it

The Microsoft Graph provider sends mail from an Outlook / Exchange Online mailbox and, with read
permission, shows that mailbox in the admin inbox. The backend signs in as an Entra application (OAuth 2.0
client-credentials flow with a **certificate**, no signed-in user, no client secret) and calls Graph
`sendMail` once per message. The request body is usually the complete MIME message the app builds for
every provider, base64-encoded, so every header (`List-Unsubscribe`, `In-Reply-To`, `References`), inline
image, and attachment (such as the ticket calendar file) is sent as built. Graph always files a copy of a
MIME `sendMail` in the sender mailbox's Sent Items, so mail that carries a credential (sign-in codes and
links, admin invitations, tickets, campaign messages with the recipient's login link) is sent in Graph's
JSON format with `saveToSentItems: false` instead; see [Sent Items](#sent-items-and-credential-mail).

It is the third choice of the **Provider** setting:

| | AWS SES | SMTP | Microsoft Graph |
|---|---|---|---|
| Credentials | Shared AWS IAM key in Secrets Manager, referenced by `AWSCredentialConfig` | Host, port, optional username and password (`SMTPProviderConfig`) | Entra tenant ID and client ID, an installed certificate whose private key is kept in the credential store (AWS Secrets Manager in production), and a mailbox scope (`MicrosoftGraphProviderConfig`, `MicrosoftGraphCertificate`) |
| Transport | SES API, raw MIME | SMTP submission | HTTPS `sendMail`: base64 MIME, or JSON for credential mail |
| Message ID recorded | SES message ID | MIME `Message-ID` | MIME `Message-ID` (none for a JSON send) |
| Delivery events | Yes, through the [SNS webhook](ses-event-tracking.md) | No | No |
| Bounced and complained addresses skipped | Yes, by the SES account-level suppression list | No | No: the site keeps no suppression list of its own, so addresses SES suppressed are mailed again |
| Provider limits | SES account quotas | The SMTP server's | Per mailbox: 30 messages per minute, 10,000 recipients per day, and the tenant's own policies ([Limits](#limits)) |

- **One provider for all app email.** Login codes, ticket emails, admin invitations, inbox replies,
  campaigns, and the test email all use the active provider. There is no per-message routing and no
  fallback: when Graph fails, the message is not re-sent through SES or SMTP.
- **Use it** when mail must leave from an Exchange Online mailbox (user or shared) and the site should
  authenticate with an app registration instead of a mailbox password.
- **Do not rely on it for bulk mail.** One mailbox carries all of the site's email within the
  [limits](#limits) below, and Microsoft recommends Azure Communication Services Email for bulk mail.

### Two layers restrict the mailbox

1. **Microsoft (Exchange Online would enforce it).** An Exchange restriction must limit the app to the I2G
   mailbox: an Application Access Policy over Entra application permissions, or RBAC for Applications
   ([step 2](#2-grant-the-approved-permissions-and-restrict-them-to-the-i2g-mailbox)). Only this layer
   limits someone who obtains the private key or an access token. Whether it holds for the UC Merced app is
   not verified yet: no allowed/denied test result exists (see [UC Merced status](#uc-merced-status-ritm0450512)).
2. **The site (defense in depth).** Each Graph configuration has a **mailbox scope**: a list of mailboxes,
   each with a permission level (*Send only*, *Read only*, or *Send and read*). The site refuses, before
   contacting Microsoft, any send as or read of a mailbox that is not listed with that permission. Nothing
   is hard-coded: the scope is data in Django admin and must match the Exchange restriction. The transport
   also refuses every Graph request except the five kinds the site needs
   ([How it behaves](#how-it-behaves)), whatever permissions the app holds.

## UC Merced status (RITM0450512)

Only what the ticket record shows is stated as fact here. Cloud Systems' statements are recorded as their
statements; nothing below has been checked against the tenant from the site's side.

| Item | On record | Status |
|------|-----------|--------|
| Approval (InfoSec, 2026-10-28) | Application `Mail.Send` and `Mail.Read` for `i2g@ucmerced.edu` only, certificate authentication, no further Graph permissions without a new InfoSec review, documented logging, monitoring, rotation, retention and revocation, and proof that access is allowed for the I2G mailbox and denied for an unrelated one | The conditions this runbook answers |
| Microsoft-side configuration, as reported by Cloud Systems on 2026-10-30 (unverified) | Entra app "Innovate2Grow" (client ID `f50cd7bc-ab45-4698-ab42-ae737a4c8adc`, tenant `f4dfe9a3-ca78-4998-b7a7-e6d0692eace6`) with application permissions **`Mail.ReadWrite` and `Mail.Send`**, restricted to `i2g@ucmerced.edu` through an "Access Policy group" that must be updated if the mailbox changes. Cloud Systems' reason for `Mail.ReadWrite`: the approved set "cannot compose email" | **Exceeds the 10/28 approval.** No InfoSec review of `Mail.ReadWrite` is on record. The site does not need it: it only calls `sendMail` (`Mail.Send`) and reads messages (`Mail.Read`), and Microsoft's permission reference says `Mail.ReadWrite` allows creating, updating and deleting mail and "does not include permission to send mail". The wording suggests an Exchange Application Access Policy, not RBAC for Applications |
| Allowed / denied test | None in the ticket | Not done. Nothing may say the tenant restriction is verified until the [access check](#validate-the-access-restriction) has passed against a designated unrelated test mailbox |
| Certificate | Self-signed RSA 3072 / SHA-256, valid until 2027-10-29, SHA-1 thumbprint `6FC515A1F6013DA98CDDDB9461460BE8A4EE872E`; private key only in the developer's macOS Keychain | To be installed on the [Install certificate](#2-install-the-certificate) page (a Keychain export is a password-protected `.p12`, which the page accepts) |
| Key storage | Intended for AWS Secrets Manager | Implemented ([Where the private key is kept](#where-the-private-key-is-kept)); the secret, its task-role write grant and its resource policy are not deployed or tested in AWS yet |
| Not evidenced | The AWS runtime, a production deploy, an end-to-end Graph send and receive | Open |

### Open items before go-live

Production refuses to switch email to Microsoft Graph until the [go-live gate](#go-live-gate) is met, so
items 1, 3 and 4 block it in code; the others need a decision, a confirmation or OIT's evidence before
go-live.

1. **Permissions.** Ask Cloud Systems to replace `Mail.ReadWrite` with `Mail.Read`. Under an access policy the
   consented permissions appear in the token's `roles`, so the access check fails while `Mail.ReadWrite` is
   granted, unless InfoSec approves it in writing and a superuser records the review's reference as
   **InfoSec Exception Reference**.
2. **Restriction evidence from OIT.** Ask Cloud Systems for the `Get-ApplicationAccessPolicy` output for the
   app, and for `Test-ApplicationAccessPolicy` results for `i2g@ucmerced.edu` (`Granted`) and for the
   designated test mailbox (`Denied`), and to confirm whether the restriction is an Application Access Policy
   or RBAC for Applications.
3. **Designated deny mailbox.** OIT / InfoSec name an existing mailbox unrelated to I2G for the denial test; a
   superuser enters it as **Access Check Deny Mailbox**.
4. **A passing access check** with the installed certificate against that mailbox, after OIT's changes have
   had time to apply (more than an hour for an access policy).
5. **Certificate only.** Ask Cloud Systems to confirm that the app registration has no client secret and no
   federated credential (Certificates & secrets). The site uses the certificate only, but either of those
   would let someone obtain tokens without it.
6. **Key storage sign-off.** InfoSec signs off the Secrets Manager design, including the task role's write
   grant on the one secret, which is an exception to the read-only rule for application credentials
   ([Where the private key is kept](#where-the-private-key-is-kept)).
7. **AWS deployment.** Deploy `aws/cicd/identity-stack.json` (the empty secret, the task-role policy and the
   resource policy) before anyone installs a certificate in production, and confirm with the account owner
   that `ecsTaskRole` has no IAM path, which the resource policy assumes.
8. **Key exposure.** Earlier builds of this branch stored the private key in a database column. If the real
   key (SHA-1 `6FC515A1…872E`) was ever entered in such a build, a development database or a shared
   environment, create a new key pair before go-live.
9. **Sending limits.** Ask Cloud Systems for the outbound spam policy and tenant limits that apply to
   `i2g@ucmerced.edu` (they can be lower than Microsoft's defaults), and to route Microsoft's "User restricted
   from sending email" alert to the I2G operators ([Limits](#limits)).
10. **Disclosures to InfoSec.** The AI scam review sends some Inbox mail to Amazon Bedrock
    ([Admin inbox](#admin-inbox)); campaign messages with `{{login_link}}` are sent without a Sent Items
    copy and therefore without the one-click `List-Unsubscribe` header
    ([Sent Items](#sent-items-and-credential-mail)); addresses SES suppressed are mailed again under Graph.
    Agree with InfoSec which records count as the logging record (admin history, recorded access checks,
    CloudTrail) and their retention ([Retention](#retention)).

Known gaps that remain (not fixed by this change): a campaign the web process is already sending keeps its
provider when the provider is switched ([Emergency revocation](#emergency-revocation)); the inbox cache keys
do not include the mailbox; the site does not log which admin opened which message; the AI scam review's
request carries the admin assistant's tool definitions; there is no app-level bounce suppression.

## Prerequisites

| Who | Does |
|-----|------|
| Cloud Systems (Entra / Exchange Online administrators) | Registers the app, adds and removes its certificates, grants its permissions and maintains the Exchange restriction |
| AWS account administrator | Deploys the identity stack (the secret and its policies) and reviews CloudTrail |
| Superuser on the site | Installs, rolls back and removes certificates, sets the deny mailbox and the InfoSec exception reference, and runs the access check |
| Staff with the **Core** app | Edit the Graph configuration and its mailbox scope, see the certificate panel and the recorded access checks |
| Staff with the **Mail** app | Select the provider under Mail → Notification Delivery, where the Graph configuration is read-only |

The sender mailbox must be an Exchange Online mailbox, user or shared. Graph cannot send as an on-premises
mailbox or as an address that has no mailbox (`404`, see the [error reference](#error-reference)).

## Microsoft-side setup

### 1. Register the application

In the Microsoft Entra admin center open **App registrations** and choose **New registration** (UC Merced:
the existing "Innovate2Grow" app).

- Supported account types: **Accounts in this organizational directory only** (single tenant).
- Leave the redirect URI empty.
- **Certificates & secrets** holds only the site's certificate: no client secret, no federated credential.

On the Overview page copy **Application (client) ID** and **Directory (tenant) ID**.

### 2. Grant the approved permissions and restrict them to the I2G mailbox

The approval is application `Mail.Send` and `Mail.Read` for `i2g@ucmerced.edu`. Never `Mail.ReadWrite`: it
allows creating, updating and deleting mail and adds nothing the site uses. Microsoft offers two ways to
restrict an app to some mailboxes; ask Cloud Systems which one is in place.

**A. Application Access Policy (what Cloud Systems reported).** The permissions are granted in Entra
(**API permissions** → Microsoft Graph → **Application permissions** → `Mail.Send`, `Mail.Read`, with admin
consent), and an Exchange policy limits them to the members of a mail-enabled security group that contains
only the I2G mailbox. In Exchange Online PowerShell:

```powershell
Connect-ExchangeOnline

New-ApplicationAccessPolicy -AppId <client-id> -PolicyScopeGroupId <group-address> `
  -AccessRight RestrictAccess -Description "I2G website mail: i2g@ucmerced.edu only"

# Evidence for InfoSec: the policy, and the result for the I2G mailbox and the designated test mailbox.
Get-ApplicationAccessPolicy
Test-ApplicationAccessPolicy -Identity i2g@ucmerced.edu -AppId <client-id>                # Granted
Test-ApplicationAccessPolicy -Identity <designated-test-mailbox> -AppId <client-id>       # Denied
```

- Admin consent alone lets an application permission reach every mailbox in the tenant; the policy is the
  only thing that narrows it. **Never delete the policy or its group while the consent exists**, and treat
  the group's membership as part of the approval: each member is a mailbox the app may use, so a new member
  needs an InfoSec review (this is the "Access Policy group" Cloud Systems mentioned).
- Microsoft notes that policy changes can take longer than an hour to apply to Graph calls, even when
  `Test-ApplicationAccessPolicy` already shows the new result.
- The consented permissions appear in the access token's `roles`, which the access check compares with the
  approval.

**B. RBAC for Applications.** No Graph permission is granted in Entra (an Entra application permission is
tenant-wide, and Exchange adds it to any scoped grant, so the scope would have no effect). Exchange role
assignments grant the two permissions inside a management scope that contains only the I2G mailbox:

```powershell
Connect-ExchangeOnline

# ObjectId is the Object ID of the enterprise application (Entra > Enterprise applications),
# not of the app registration.
New-ServicePrincipal -AppId <client-id> -ObjectId <enterprise-app-object-id> -DisplayName "I2G website mail"
New-ManagementScope -Name "I2G mailbox" -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'i2g@ucmerced.edu'"
New-ManagementRoleAssignment -App <client-id> -Role "Application Mail.Send" -CustomResourceScope "I2G mailbox"
New-ManagementRoleAssignment -App <client-id> -Role "Application Mail.Read" -CustomResourceScope "I2G mailbox"

# InScope must be True for i2g@ucmerced.edu and False for the designated test mailbox.
Test-ServicePrincipalAuthorization -Identity <client-id> -Resource i2g@ucmerced.edu
Test-ServicePrincipalAuthorization -Identity <client-id> -Resource <designated-test-mailbox>
```

- `Test-ServicePrincipalAuthorization` ignores permissions granted in Entra, so it can show a restriction
  that a leftover Entra grant bypasses; the [access check](#validate-the-access-restriction) tests the real
  effect.
- Role-assignment grants never appear in the token's `roles`, so the access check's `roles` line is a WARN.
- Exchange can take 30 minutes to 2 hours to apply a change, and requests fail with `403` until it has.
- Microsoft's RBAC for Applications article (see [Sources](#sources)) describes moving from Application
  Access Policies to RBAC for Applications. Whether to move is Cloud Systems' decision; the site works with
  either.

### 3. Create the key pair and certificate

The app proves its identity with a certificate (Microsoft's `private_key_jwt`): it signs a short-lived
assertion with the private key, and Entra checks it against the uploaded certificate. The private key never
crosses the network and never goes to OIT. Create it on the operator's own laptop, not on a shared server.

An RSA key of at least `GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS` (2048) bits and a self-signed certificate are
enough; Entra only checks that the key matches. With OpenSSL (it prompts for a passphrase and writes an
encrypted private key):

```bash
openssl req -x509 -newkey rsa:3072 -sha256 -days 365 \
  -subj "/CN=I2G website mail" -keyout i2g-graph.key -out i2g-graph.crt

# The DER .cer file for OIT, and its SHA-1 thumbprint (Entra shows it without the colons).
openssl x509 -in i2g-graph.crt -outform der -out i2g-graph.cer
openssl x509 -in i2g-graph.cer -inform der -noout -fingerprint -sha1
```

Or create the certificate in macOS Keychain Access and export the certificate (`.cer`) and the identity
(`.p12`, protected by a password).

Send OIT the `.cer` file and its SHA-1 thumbprint, and ask them to add it to the app under **Certificates &
secrets** → **Certificates**. Keep the private key (the encrypted `.key` file or the `.p12`) on the laptop
until it is installed in the admin; then keep no other copy than the one the site stores, unless InfoSec
asks for an offline backup.

### Thumbprints

| Value | Where it appears | Use it to |
|-------|------------------|-----------|
| SHA-1 thumbprint, 40 hex characters (`6FC515A1…872E`) | Entra **Certificates & secrets** (Thumbprint), the ticket, `openssl … -fingerprint -sha1`, the admin's certificate panel and access check header | Compare the admin with Entra; the **Expected SHA-1 thumbprint** field of the Install page; ask OIT to add or remove a certificate |
| SHA-256 fingerprint, 64 hex characters | The admin's certificate panel | Compare with `openssl x509 … -fingerprint -sha256` |
| `x5t#S256` (base64url SHA-256) | The header of each client assertion the site signs; never shown in Entra | Nothing: it is how Entra finds the certificate |
| Key version | The certificate panel ("Stored in AWS Secrets Manager, version …") and the access check header | Match CloudTrail entries and the secret's versions |

## Configure in Django admin

The Graph configuration, its mailbox scope and the certificate's public data are in the database; the
private key is in the credential store ([Where the private key is kept](#where-the-private-key-is-kept)).
Nothing is read from code or environment variables. Set up and validate the configuration first, while
another provider still sends, then select Graph.

### 1. Create the Graph configuration

Open **Site Settings → Service Credentials → Microsoft Graph** (`/admin/core/microsoftgraphproviderconfig/`; the
**Configure** link on the Microsoft Graph card under Broadcast Delivery → Email Sending Method also leads there) and add a
configuration:

| Field | Value |
|-------|-------|
| **Config Name** | Label for this configuration (default `Default`). |
| **Active** | Tick it. Only one Graph configuration can be active; activating one deactivates the others. |
| **Tenant ID** | Directory (tenant) ID as a GUID, or a verified domain such as `contoso.onmicrosoft.com`. `common`, `organizations`, and `consumers` are rejected. |
| **Client ID** | Application (client) ID of the Entra app registration (a GUID). |
| **Sender Mailbox** | `i2g@ucmerced.edu`. Blank means the **From Email** address. The admin inbox reads this mailbox too. |
| **Mailbox scope** (inline rows) | One row: mailbox `i2g@ucmerced.edu`, permission **Send and read (Mail.Send + Mail.Read)**. |
| **Access Check Deny Mailbox** | Superusers only. The unrelated test mailbox OIT / InfoSec designated for the denial test ([Validate the access restriction](#validate-the-access-restriction)): a plain address, outside the scope, not the sender mailbox or **From Email**. |
| **InfoSec Exception Reference** | Superusers only, and only after InfoSec has approved in writing Graph permissions beyond `Mail.Send` and `Mail.Read`: the reference of that review. Leave it blank otherwise. |

Save, then use the panel above the form. It shows the **current certificate**: SHA-1 thumbprint (as Entra
lists it), SHA-256 fingerprint, subject, serial, validity with an expiry badge (amber from
`GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS`, default 60, and red from `GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS`,
default 14, days before expiry), where the key is stored and its version, and the Entra check result; the
**previous certificate** kept for rollback; and the **latest access check** (verdict, date, certificate,
deny mailbox, the token's roles, a link to the recorded result, and whether it is go-live evidence). The
form itself has no certificate, key or secret input.

**Tenant ID** and **Client ID** are read-only while a certificate is installed: a certificate is tested for
one tenant and app. To move to another app, set up a standby configuration for it, install its certificate
there, run the access check there (**Run access check** works on an inactive configuration), and then
activate it. While Notification Delivery sends through Graph, activating a configuration needs what
switching email to Graph needs (see [Go-live gate](#go-live-gate)), and the active configuration's tenant
and app cannot change at all: select another provider first.

### 2. Install the certificate

An admin with **Core** access chooses **Install certificate** on the saved configuration's panel.
Save a new configuration with **Save and continue editing** to reach this panel. It is a separate page,
not the configuration form: nothing entered is kept in the session or cache, the key and password inputs are never shown again,
and error reports hide them. It takes either:

- **.p12 / .pfx file** with **Password / passphrase** (what macOS Keychain exports), or
- **Certificate** (PEM or base64, pasted) or **…or certificate file** (the DER `.cer`, or a `.crt` / `.pem`),
  and **Private key** (pasted) or **…or private key file**: PEM PKCS#8 or PKCS#1, optionally encrypted, with
  its passphrase in **Password / passphrase**.

Each input is at most `GRAPH_CERTIFICATE_MAX_INPUT_BYTES` (64 KiB). Enter the SHA-1 thumbprint OIT
confirmed in **Expected SHA-1 thumbprint** (case, colons and spaces are ignored): the install stops when
the certificate differs.

Installing (`apps.core.services.email.graph.credential.lifecycle`) works in this order:

1. **In memory:** the input holds exactly one certificate, and the certificate input no private key; the
   key is RSA of at least `GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS` bits and belongs to the certificate; the
   certificate is valid now (`GRAPH_CERTIFICATE_CLOCK_SKEW_SECONDS`, default 300, of clock skew allowed).
   The current certificate is refused as "already current", and the previous one is refused with a
   pointer to **Roll back to previous**.
2. **One token request to Entra** with the key (`GRAPH_CERTIFICATE_CHECK_TIMEOUT_SECONDS`, default 10):

   | Entra's answer | Inactive configuration | Active configuration |
   |----------------|------------------------|----------------------|
   | A token | Installed | Installed |
   | `AADSTS700027` (the certificate is not registered on the app yet) | Installed, shown as not trusted | Refused: it would stop email |
   | Entra cannot be reached | Installed | Refused |
   | `AADSTS700016` (no such app), `AADSTS90002` (no such tenant), `AADSTS7000112` (app disabled), any other rejection | Refused | Refused |

3. **The key is written to the credential store** as a new version, outside any database transaction.
4. **One short transaction pins it:** the new certificate becomes current, the replaced one previous, and an
   older previous one is marked removed. The admin history (`LogEntry`) records who did it, with the
   thumbprint and key version and no key material. The page then shows the SHA-1 thumbprint, the expiry and
   the key version.

A failure before step 4 leaves the site exactly as it was. Every message is fixed text and never contains
key material. A re-issued certificate for the same key can be installed with the private key left blank:
it reuses the installed key version only when its public key matches; any other certificate without a key
is refused.

The panel also offers **Roll back to previous** (after a fresh token test with the previous key), **Remove
(emergency)** ([Emergency revocation](#emergency-revocation)) and **Download .cer** (the public certificate,
for OIT). Staff with the **Core** app can install or replace a certificate and download the public `.cer`.
Rollback, emergency removal, access checks and approval-evidence fields remain superuser-only.

### 3. Validate, then select Graph

1. Set **Access Check Deny Mailbox** and run the [access check](#validate-the-access-restriction)
   (**Run access check**). In production, Notification Delivery refuses Microsoft Graph until a run with the
   current certificate matches the approval ([go-live gate](#go-live-gate)).
2. Open **Email Sending Method**: in the sidebar group **Broadcast Delivery**
   (`/admin/mail/sending-method/`). The **Microsoft Graph** card says whether Graph could send now and, if not, why
   (the same check as switching, so the go-live gate applies). Once it is **Ready**, select **Send test** on
   that card to send a test email through Graph while another method still sends everything else.
3. Select **Use for email** on the Microsoft Graph card. (The same switch is the **Provider** field under
   **Email Sender** on **Edit Notification Delivery**, which also sets **Active**, **From Name** and
   **From Email**, here `i2g@ucmerced.edu`.) The Graph panel shows the
   configuration read-only (with the certificate's SHA-1 thumbprint and expiry, the mailbox scope and the
   latest access check); this page cannot change it. Staff with the **Core** app get a link to the
   configuration page.
4. Do the [first live check](#first-live-check).

- The **From Email** and the sending mailbox must both be in the scope with send permission; otherwise
  saving stops under **Provider** with "An active Microsoft Graph configuration whose mailbox scope lets
  the sender mailbox and the From address send is required before activation."
- Choosing AWS SES or SMTP later hides the Graph panel and keeps the saved Graph settings. The AWS panel on
  the same page is always saved and is still used for SMS.
- An active configuration cannot be deleted. An inactive one with recorded access checks cannot be deleted
  either, so the evidence is kept. Deleting an inactive one without them deletes its scope rows and
  certificate rows (the key versions stay in the store, unpinned).
- While Notification Delivery sends through Graph, the configuration page refuses a save that would stop
  email: deactivating the sending configuration, activating a standby that cannot send, or a mailbox scope
  or sender mailbox that no longer lets the sender and the **From Email** send. It also refuses activating
  a standby that email could not switch to (see [Go-live gate](#go-live-gate)) and any change of the
  active configuration's tenant or app. Select another provider first.
- A successful test reports `Test email sent to <address> via Microsoft Graph (config: <name>).` That
  means Graph accepted the message (HTTP 202), not that it was delivered. A failure reports
  `Failed to send test email: <message>`; the messages are explained in the
  [error reference](#error-reference).

### Mailbox scope and permission levels

| Permission level | The site may | Microsoft must allow |
|------------------|--------------|----------------------|
| Send only (Mail.Send) | send as the mailbox | `Mail.Send` for the mailbox |
| Read only (Mail.Read) | list and open messages in its Inbox and Sent Items | `Mail.Read` for the mailbox |
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
- Adding a mailbox here does not grant anything at Microsoft; the Exchange restriction must also include it.
  Adding a mailbox or permission beyond the approval needs a new InfoSec review.
- The scope model is on the safe-ORM denylist, so the `i2g-admin` CLI and the AI assistant cannot read
  or change it.

## Where the private key is kept

The private key is never stored in the database, code, images, task definitions or environment variables.
`apps.core.services.credential_store` keeps it in the store `CREDENTIAL_STORE_BACKEND` selects:

| Environment | Store | Where |
|-------------|-------|-------|
| Production | `secretsmanager`, required by `CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER`: with any other store the `core.E002` system check stops every management command, container start-up and the worker included | The secret `itg/backend/microsoft-graph/certificate-key` (`CREDENTIAL_STORE_SECRETS`) in `CREDENTIAL_STORE_AWS_REGION` (`us-west-2`) |
| Local development | `local_file` | `src/data/credential-store/` (gitignored and excluded from the image): a 0700 directory of 0600 files. Throwaway keys only |
| Tests | `memory` | Process memory |

- **Versions.** Each install writes one new version holding the canonical unencrypted PKCS#8 PEM of the key
  and the SHA-256 of its public key (schema `i2g.graph-key/1`): no certificate, no `.p12`, no password. The
  version token is derived from that hash, so storing the same key again writes nothing new. A new version
  gets the staging label `CREDENTIAL_STORE_STAGED_LABEL` (`I2G-STAGED`), and the site never asks for
  `AWSCURRENT` on a write, so a write changes nothing on its own. The one exception is Secrets Manager's
  own: the first version written to the empty secret also gets `AWSCURRENT` (the local and memory stores
  copy that).
- **The pin decides.** The `MicrosoftGraphCertificate` row stores the secret's ARN and the version ID; that
  pin, not a Secrets Manager label, decides which key signs. After the pin commits on the active
  configuration, the site moves `AWSCURRENT` to the pinned version, best effort, so the console shows the
  version in use; Secrets Manager then puts `AWSPREVIOUS` on the version it left, which is the rollback
  certificate's.
- **Pinned versions can lose every label.** All configurations share the one secret, and `I2G-STAGED`
  moves to each newly written version. A version pinned only by a standby configuration, or a rollback
  version whose `AWSCURRENT` move failed (a WARNING in the log), keeps no label once another version is
  written. AWS treats a version without a label as deprecated and may delete it once the secret holds many
  versions (AWS documents the limit as about 100; verify the current rule before relying on it), and the
  pinned key would then be unreadable. One install per rotation stays far below that, but after unusual
  activity check the labels with
  `aws secretsmanager list-secret-version-ids --secret-id itg/backend/microsoft-graph/certificate-key
  --include-deprecated` (the version IDs are on the certificate panel). Storing the same key again reuses
  its version without relabelling it, so a configuration whose pinned version shows no label needs a
  [rotation](#rotate-the-certificate) to a new key pair.
- **Reads.** On a token-cache miss (about once an hour per process) the backend reads exactly the pinned
  ARN and version, checks that the key matches the certificate's public key, signs one client assertion and
  drops the key. Nothing caches the key; a mismatch or an unreadable version is an error, never a fallback
  to another version.
- **Timeouts.** Secrets Manager calls use `CREDENTIAL_STORE_CONNECT_TIMEOUT_SECONDS` (3),
  `CREDENTIAL_STORE_READ_TIMEOUT_SECONDS` (5) and `CREDENTIAL_STORE_TOTAL_MAX_ATTEMPTS` (3, the first
  included).

AWS permissions (`aws/cicd/identity-stack.json`; deployment notes in
[Production](../deployment/production.md#microsoft-graph-certificate-key)):

- The secret is created empty, with `DeletionPolicy` and `UpdateReplacePolicy` `Retain`. Never set a value
  in the console: only the backend adds versions.
- `ecsTaskRole` (the backend web and worker containers) may `GetSecretValue`, `DescribeSecret`,
  `PutSecretValue` and `UpdateSecretVersionStage` on this one secret, and is explicitly denied deleting,
  restoring, updating, rotating or replicating it, changing its resource policy, and tagging it.
- The secret's resource policy (with `BlockPublicPolicy`) denies reading the value and writing versions to
  every principal except `ecsTaskRole`. No person or other role can read the key through IAM; break-glass
  means an account administrator changes the resource policy, which CloudTrail records.
- **This is an exception** to the rule that the ECS task role has read-only access to application
  credentials ([Production](../deployment/production.md#application-aws-credentials-and-background-jobs)):
  the backend must write a version when a Core admin installs a certificate. It needs InfoSec sign-off
  ([Open items](#open-items-before-go-live)).

What this means: code running as the backend can read the key, as it can every credential the backend
uses, and can add versions, but it cannot delete the secret or change who may read it, and a version no
row pins is never used.

## Validate the access restriction

The access check asks Microsoft directly, bypassing the site's own scope check, what the Entra app may do
and compares it with the InfoSec approval (`Mail.Send` and `Mail.Read` for the I2G mailbox). A superuser
runs it with **Run access check** on the Graph configuration's page (production has no ECS Exec), or from a
shell:

```bash
cd src && python manage.py verify_graph_access
```

Before the first run a superuser sets **Access Check Deny Mailbox**: an existing mailbox outside the scope,
designated by OIT / InfoSec for the denial test (a plain email address, not another name of a scoped
mailbox). `--deny-mailbox <address>` tries another one, but only runs against the designated mailbox count
as go-live evidence; `--no-send` skips the send probes and makes the run incomplete. Each run requests a
fresh token with the current certificate and records one **Microsoft Graph Access Check** row (Core app,
read-only): the certificate, the deny mailbox, every probe line, the token's roles and the verdict. No token,
response body or message content is stored. The output starts with the time (UTC), the tenant and client
ID, "certificate only" with the SHA-1 thumbprint and key version, the deny mailbox, the approved roles and
any recorded exception.

| Check | Mailbox | Expected |
|-------|---------|----------|
| `token` | | issued for the current certificate |
| `roles` | | the token's `roles` claim within `GRAPH_APPROVED_APPLICATION_ROLES` (default `Mail.Send`, `Mail.Read`) |
| `folder`, `list`, `value` | each scoped mailbox with read permission | `200`: the Inbox, the newest message with its preview (`$top=1&$select=id,bodyPreview`), and the first `GRAPH_ACCESS_CHECK_MIME_MAX_BYTES` (default 4096) bytes of its raw MIME, which are discarded. An empty Inbox makes `value` INCONCLUSIVE, so the run is not a complete validation: run it again once the Inbox holds a message (the `send` probe delivers one) |
| `send` | each scoped mailbox with send permission, listed by address | `202`: a MIME probe email to itself (a copy stays in its Sent Items) |
| `read+` | each scoped mailbox with send permission only | for the record: a `200` is a WARN, because an access policy limits mailboxes, not permissions, so only the site's scope stops reading it |
| `folder`, `list` | the deny mailbox | `403` |
| `send` | as the deny mailbox, addressed to the I2G mailbox | `403` |
| `sendas` | the I2G mailbox, with the deny mailbox as From | `403` (`ErrorSendAsDenied`): the I2G mailbox holds no Send As or Send on Behalf right on it. A `202` is a FAIL |

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
(Mail.ReadWrite) · Verdict: DOES NOT MATCH THE APPROVAL`, which is what the configuration Cloud Systems
reported would give. The command exits non-zero unless the verdict is **Matches the approval**: the
restriction holds, nothing failed or was skipped, and the roles are within the approval or covered by a
recorded exception. It then prints `Go-live evidence: present` or what is missing. Run it after setup,
after any Exchange or Entra change, and after rotation; wait at least an hour after OIT changes an access
policy. The recorded rows, together with OIT's `Test-ApplicationAccessPolicy` output, are the validation
evidence for InfoSec.

### Go-live gate

Where `GRAPH_REQUIRE_ACCESS_EVIDENCE` is on (production; off locally and in tests), Mail → Notification
Delivery can switch email to Microsoft Graph only when the latest access check run with the current
certificate matched the approval, used the designated deny mailbox, and is at most
`GRAPH_ACCESS_EVIDENCE_MAX_AGE_DAYS` (default 30) days old. A role beyond today's approval still needs an
exception reference at the time of the switch, so clearing the reference, or narrowing
`GRAPH_APPROVED_APPLICATION_ROLES`, withdraws the evidence. Refused saves say why under **Provider**
(`Email cannot switch to Microsoft Graph yet: …`).

The same rule applies whenever email that is already on Graph would move to another Entra app or
certificate: activating another configuration on its page is refused under **Active** (`… can become the
active one only when email could switch to it: …`) unless that configuration's own latest access check is
evidence, and the active configuration's tenant and app cannot change while email is on Graph. In every
environment, gate on or off, the configuration email switches to must hold a current certificate that Entra
issued a token with: one installed on an inactive configuration before OIT registered it says "not trusted"
until an access check (or a re-install) gets a token with it.

Editing a configuration that already sends through Graph is not blocked otherwise, and neither is installing
or rolling back a certificate on it, because the check needs the new certificate installed first; the panel
then shows the evidence as missing until the check is run again.

## Rotate the certificate

Entra accepts several certificates on one app, and the Install page refuses, on the active configuration,
any certificate Entra does not accept yet, so rotation needs no downtime when done in this order:

1. **Laptop:** create a new key pair and certificate ([step 3](#3-create-the-key-pair-and-certificate)).
2. **OIT:** send the new `.cer` and its SHA-1 thumbprint, and ask Cloud Systems to add it to the app. The
   old certificate keeps working.
3. **Admin (Core access):** once OIT confirms, **Install certificate** with the new pair and the expected
   SHA-1 thumbprint. The site writes a new key version, tests it with Entra, and switches the pin; the
   replaced certificate is kept as previous.
4. **Admin (superuser):** **Run access check** and send a test email. Evidence recorded for the old certificate
   does not count for the new one.
5. **OIT:** after a day without problems, ask Cloud Systems to remove the old certificate (by its SHA-1
   thumbprint). From then on **Roll back to previous** fails its token test, as it should.
6. **Laptop:** destroy the remaining copies of the old key.

The new key applies to the next token request in every process; no restart is needed. If something is
wrong before step 5, **Roll back to previous** restores the old certificate after a fresh token test.
Rotate before the `GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS` threshold (default 14 days before expiry;
reminders start at `GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS`, default 60, see [Monitoring](#monitoring)), and
at once if the key may have been exposed ([Emergency revocation](#emergency-revocation)). A re-issued
certificate for the same key (new validity, same key) is installed with the private key left blank.

## Check the stored configuration

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
`--strict` run fails two weeks before the certificate stops email. It reads stored settings only, contacts
neither Microsoft nor AWS, and does not report access-check evidence; the access check and **Send Test
Email** prove the credentials.

## How it behaves

- **Request flow.** The backend requests an access token from
  `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token` (client-credentials grant, scope
  `https://graph.microsoft.com/.default`) with a client assertion: a JWT signed with the private key
  (`PS256`, header `x5t#S256` = the certificate's SHA-256 thumbprint, valid for
  `GRAPH_CLIENT_ASSERTION_LIFETIME_SECONDS`, default 5 minutes, a fresh `jti` each time), never the key
  itself. It then sends
  `POST https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail` with `Content-Type: text/plain` and
  the base64 MIME as the body, or with `Content-Type: application/json` for credential mail. Only those
  two hosts are used, over TLS 1.2 or later, without following redirects or using proxy environment
  variables, with a `GRAPH_REQUEST_TIMEOUT_SECONDS` (default 30) timeout per request and at most
  `GRAPH_MAX_RESPONSE_BYTES` (64 KiB) of each answer read. The backend and worker containers need outbound
  HTTPS to both.
- **Only five kinds of request.** The transport (`transport.py`, `ALLOWED_REQUESTS`) refuses, before
  opening a connection, every request except the token request, `POST …/users/{mailbox}/sendMail`,
  `GET …/mailFolders/{inbox|sentitems}/messages`, `GET …/mailFolders/inbox` (the access-check probe) and
  `GET …/messages/{id}/$value`. No code path can create a draft, reply, move, flag, mark read or delete
  mail, whatever permissions the Entra app holds. This keeps the site itself from using `Mail.ReadWrite`
  if OIT leaves it granted, but it does not limit someone who obtains the key or a token. A refused request
  is the permanent error `The site does not make this Microsoft Graph request.`
- **Message ID.** `sendMail` answers `202 Accepted` with no body and no message ID, so the app records
  the `Message-ID` header it generated as the provider message ID in the Email Log (`RecipientLog`,
  provider `graph`), as it does for SMTP. Its domain part is the **From Email** domain (`<…@ucmerced.edu>`
  for `i2g@ucmerced.edu`), never the server's internal host name. A JSON send sets no `Message-ID`
  (Exchange assigns one) and reports none, so a campaign message sent with a login link has an empty
  provider message ID in the Email Log.
- **202 means queued, not delivered.** A later failure, such as an unknown recipient, a rejection by the
  recipient's server or a sending restriction, comes back as a non-delivery report in the sender mailbox's
  Inbox. The app shows that Inbox to admins (see [Admin inbox](#admin-inbox)) but does not parse it, and
  receives no delivery events, so Email Log rows stay `sent`; they never become `delivered`, `bounced`, or
  `complained`, as with SMTP. Someone should watch the sender mailbox for non-delivery reports and untick
  **Subscribed** on contacts whose address bounces. The Delivery Dashboard charts SES CloudWatch metrics only
  and says so in a notice while another provider is active.
- **Sent Items.** A MIME `sendMail` is always saved in the sender mailbox's Sent Items folder; credential
  mail is sent as JSON and leaves no copy. See [Sent Items and credential mail](#sent-items-and-credential-mail).
- **Bcc.** The MIME builder writes no Bcc header and Graph has no separate envelope for MIME, so a MIME
  message with a Bcc recipient is refused as a permanent error rather than silently not delivered to it. The
  JSON form has its own Bcc list and delivers it. No current feature sends Bcc.
- **Tokens.** Access tokens are kept only in each process's memory (never in the database, the cache, or
  on disk), keyed by tenant, client ID, the pinned key version and the certificate thumbprint, and renewed
  shortly before they expire. Each process therefore requests its own token about once an hour. A `401` or
  `403` from Graph drops the cached token, so the next request gets a new one: that picks up changes to the
  app's Entra permissions, but Exchange applies access-policy and role-assignment changes on its own
  schedule (more than an hour) whatever the token.
- **No retry inside the provider.** One request is made per message. Retrying is left to the caller
  (see the [error reference](#error-reference)), and an uncertain outcome is never retried
  automatically.
- **Admin access.** Staff granted the **Core** app can open the configuration and install or replace its
  certificate. Only a superuser can roll back or remove a certificate or run the access check;
  **Mail → Notification Delivery** shows the configuration read-only. Changelist filters on secret-looking field names (`?private_key__regex=…`)
  are refused with `400` on every admin page. The configuration, its scope, its certificates and its access
  checks are on the safe-ORM denylist, so the `i2g-admin` CLI and the AI assistant cannot read or change
  them. Error messages and log lines carry no key, token, or response body.

| Concern | Location |
|---------|----------|
| Sending, token cache, HTTPS and its request allowlist, error mapping | `src/apps/core/services/email/graph/` (`provider.py`, `auth.py`, `transport.py`, `errors.py`) |
| JSON `sendMail` body for credential mail | `src/apps/core/services/email/graph/json_message.py` |
| Certificate facts and client assertions | `src/apps/core/services/email/graph/certificate.py` |
| Certificate input, stored key, Entra test, install / rollback / remove, expiry | `src/apps/core/services/email/graph/credential/` |
| Credential store (Secrets Manager, local file, memory) and its system checks | `src/apps/core/services/credential_store/`, `src/apps/core/checks.py` |
| Mailbox scope enforcement | `src/apps/core/services/email/graph/access.py` |
| Reading the mailbox (`Mail.Read`) | `src/apps/core/services/email/graph/mailbox.py`, `src/apps/mail/services/inbox/graph_backend.py` |
| Sent mail access in the admin inbox | `src/apps/mail/admin/inbox/helpers.py` (`sent_mail_restricted`, `sent_mail_denied`) |
| Access validation (probes, roles, verdict, evidence) | `src/apps/core/services/email/graph/access_check/`, `manage.py verify_graph_access` |
| Recorded access checks and the go-live gate | `src/apps/core/models/base/service_credentials/microsoft_graph_access_check.py`, `EmailServiceConfig.validate_activation` |
| Provider selection | `src/apps/core/services/email/registry.py` |
| Settings and scope models | `src/apps/core/models/base/service_credentials/microsoft_graph.py` |
| Installed certificates (public data + key pointer) | `src/apps/core/models/base/service_credentials/microsoft_graph_certificate.py` |
| Certificate pages, certificate panel, Run access check, recorded checks, mailbox scope inline and its guard | `src/apps/core/admin/service_credentials/microsoft_graph*.py` |
| Notification Delivery (selects the provider; Graph read-only) | `src/apps/mail/admin/settings/` |
| Settings (`GRAPH_*`, `CREDENTIAL_STORE_*`) | `src/config/settings/base/integrations/microsoft_graph/`, `src/config/settings/base/integrations/credential_store/` |
| The secret and its IAM and resource policies | `aws/cicd/identity-stack.json` |

## Sent Items and credential mail

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
- **Campaign messages that contain the recipient's login link** (`{{login_link}}` in the subject or body,
  for a recipient who is a member): the link signs in for `login_link_validity_days`, possibly more than
  once. This is decided per message, so the same campaign's messages to manual addresses (no link) stay
  MIME.

The JSON form carries the subject, one body (the HTML body when there is one, otherwise the text body), To,
Cc, Bcc, Reply-To, attachments (inline ones keep their Content-ID, so the ticket barcode still displays) and
custom headers whose names start with `x-`. Graph accepts no other custom header in this form, so any other
header is left out and its name logged at WARNING
(`Microsoft Graph JSON sendMail cannot carry these headers, so they were left out: …`). The marked messages
set none: a campaign message with a login link is built without `List-Unsubscribe` and
`List-Unsubscribe-Post` under Graph, so mailbox providers show no one-click unsubscribe for it, and the
recipient unsubscribes through the footer link (present when the campaign includes the unsubscribe
header). This is a deliberate trade-off: a live sign-in link must not sit in a folder other people can
read. Through SES or SMTP the same message keeps both headers.

Everything else stays MIME and keeps a Sent Items copy: campaign messages without a login link (one copy
per recipient, with `List-Unsubscribe`), inbox replies, security and subscription notices, the test email and
access-check probes. Only superusers can open Sent mail in **Mail → Inbox** (see
[Admin inbox](#admin-inbox)); the M365 admins should keep human Full Access to the mailbox to a minimum.
Set a retention policy for the folder (the period is a records-policy decision) and watch the mailbox size:
a full mailbox makes Graph answer `507`, and sending stops until space is freed.

## Admin inbox

When the active Graph configuration grants read permission on its sending mailbox, **Mail → Inbox** reads
that mailbox through Graph instead of Gmail IMAP; otherwise the Gmail import account is used as before.
The page shows the mailbox and `Microsoft Graph` as the source. An expired or removed certificate makes the
configuration count as not configured, so the inbox then falls back to the Gmail import account, if one is
configured.

- It lists the newest messages of **Inbox** or **Sent Items**
  (`GET /v1.0/users/{mailbox}/mailFolders/{inbox|sentitems}/messages`) and opens a message as its original
  MIME (`GET /v1.0/users/{mailbox}/messages/{id}/$value`), so the scam detector still sees
  `Authentication-Results`, `Reply-To`, and `Return-Path`, and replies keep `In-Reply-To` / `References`.
- **Sent mail is for superusers only.** Sent Items holds what the site sends as MIME (campaigns, replies,
  notices, and anything sent before credential mail went out as JSON), so other staff with the Mail app see
  no **Sent** tab, a request for the Sent folder shows the
  Inbox instead, and opening or replying to Sent mail answers `403`. A Graph message ID is unique in the
  whole mailbox rather than per folder, so any message whose sender is the sending mailbox or the
  **From Email** counts as Sent mail too, whichever folder the link names (a reply quotes the original, so
  it is refused like opening it). In the Inbox list such a message keeps its row, sender and date, but shows
  `(Sent from the site's own address: shown to superusers only)` instead of its subject and opening text. If
  the inbox backend cannot be resolved, Sent mail stays hidden. The Gmail IMAP inbox is unchanged.
- **AI scam review (Amazon Bedrock).** Opening or previewing an Inbox message whose rule score falls in the
  medium band sends, for a second opinion, the sender's name and address, Reply-To, subject,
  `Authentication-Results` and the first 4,000 characters of the body (the text part, else the HTML) to
  Amazon Bedrock. It uses the model of the active AI settings (`SystemIntelligenceConfig`) and the region
  and IAM key of `AWSCredentialConfig`. The site keeps no copy of the request; whether Bedrock
  model-invocation logging is on is an AWS account setting this repository does not manage. The review runs
  whenever AWS and the AI settings are configured; there is no separate switch. The request also carries the
  admin assistant's query-tool definitions: the prompt tells the model not to call them, but if it does, the
  site runs those read-only database queries and returns the results to Bedrock (a behaviour of the shared
  Bedrock client that predates Graph; see [Open items](#open-items-before-go-live)).
- **No AI review of Sent mail.** Sent mail, by folder or by sender as above, keeps the rule score only and is
  never sent to Bedrock: the site wrote it, and it can hold live codes (a password-reset code scores in the
  medium band because of the word "password").
- **Replies.** To and Cc must be plain addresses (`name@example.com`, `o'brien@example.com`); a quoted local
  part, a display name (`Name <addr>`), a comment, an address literal, a non-ASCII domain or a line break is
  refused with `Use plain email addresses such as name@example.com in To and Cc.` before anything is sent,
  because the To address is copied from the original sender's From header. This applies with every inbox
  backend and provider. The pages escape addresses, and the confirmation is shown as text, never as HTML.
- The site only reads: opening a message does not mark it read in Outlook, and nothing is moved or deleted
  (see [Only five kinds of request](#how-it-behaves)). Replies are sent through the email provider (Graph
  `sendMail`, MIME, with a Sent Items copy).
- **Caching.** Lists are served from the site cache for 5 minutes and opened messages for 30 minutes, as with
  IMAP; **Refresh** reloads the list. The cache keys name the folder and message but not the mailbox, so
  after changing the scope or the sender mailbox press **Refresh**: an opened message of the old mailbox can
  still be served for up to 30 minutes. A message larger than `GRAPH_INBOX_MESSAGE_MAX_BYTES` (25 MiB) is not
  shown; open it in Outlook. A list reads at most `GRAPH_INBOX_LIST_MAX_BYTES` (2 MiB) and
  `GRAPH_INBOX_MAX_LIST_LIMIT` (100) messages.
- **Failures.** A list that cannot be loaded shows "Inbox is not available…" (or "Inbox could not be
  loaded. Check server logs."); a message that cannot be opened, including one over the size limit, shows "Message
  could not be loaded. Check server logs." A refused read writes the WARNING
  `Microsoft Graph mailbox read was refused: status=<status> code=<code> request_id=<id>` plus the view's
  own WARNING (`Inbox fragment could not be loaded: …` or `Inbox message uid=… could not be loaded: …`);
  token and connection failures write only the view's line.
- **No read audit on the site.** A successful list or open writes no application log line, so the site does
  not record which admin opened which message. Microsoft's `MailItemsAccessed` audit names only the app,
  and a cached message never reaches Microsoft.

## Monitoring

| Signal | Where | Action |
|--------|-------|--------|
| `Microsoft Graph sendMail was not accepted: status=… code=… request_id=…` (WARNING) | Backend and worker logs (CloudWatch Logs) | Alert on a burst; see the [error reference](#error-reference). |
| `Microsoft Graph mailbox read was refused: …` and `Inbox fragment could not be loaded: …` (WARNING) | Backend logs | A `403` means the Exchange restriction changed; run the access check. |
| `Microsoft rejected the Graph credentials (…)` | Email Log, Background Jobs **Last error**, test email | Certificate or app problem; see [Access token requests](#access-token-requests). |
| `The Microsoft Graph private key could not be read: …` | Email Log, Background Jobs **Last error**, test email | The secret, its version or the task role's access; see [Refused before any request is made](#refused-before-any-request-is-made). |
| `Microsoft Graph certificate expiry warning: <n> days left; …` (WARNING, hourly) | Worker logs, from `GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS` (default 60) days before the active configuration's certificate expires | Rotate ([Rotate the certificate](#rotate-the-certificate)). |
| Certificate expiry | The panel's expiry badge (amber at the warning, red at `GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS`, default 14); `verify_service_configs --strict` fails from the critical threshold while Graph is selected | Rotate before the critical threshold. |
| Certificate changes | Admin history (`LogEntry`) of the Graph configuration: install, rollback and removal, with the actor, thumbprint, key version and reason | Review after any change. |
| Access check | **Microsoft Graph Access Checks** in the admin (Core app); the panel's **Go-live evidence** line | Re-run after any Entra / Exchange change or certificate rotation. |
| Use of the key secret | CloudTrail for `itg/backend/microsoft-graph/certificate-key`: `GetSecretValue`, `PutSecretValue`, `UpdateSecretVersionStage`, resource-policy changes | Only `ecsTaskRole` sessions are expected: reads about hourly per process, writes only when a Core admin installs a certificate. |
| Sign-ins of the app | Entra → Enterprise applications → the app → **Sign-in logs** (service principal sign-ins) | Unexpected IPs or failures. |
| Mailbox activity | Microsoft Purview audit log for `i2g@ucmerced.edu` (`Send`, `MailItemsAccessed`), run by the M365 admins | Investigations. |
| Non-delivery reports, mailbox size | The I2G Inbox and Sent Items | Watch for bounces and sending restrictions (`550 5.1.8`); a full mailbox stops sending (`507`). |

Suggested CloudWatch metric filters: `"Microsoft Graph sendMail was not accepted"`,
`"Microsoft Graph mailbox read was refused"`, `"Microsoft rejected the Graph credentials"` and
`"The Microsoft Graph private key could not be read"`, each with an alarm on a count above the normal
baseline over 15 minutes, and `"Microsoft Graph certificate expiry warning"` with an alarm on any match. They
are suggestions: this repository creates no alarms. Running `verify_service_configs --strict` after each
deploy also catches certificate expiry.

## Retention

- **Mailbox.** Every MIME message the site sends stays in Sent Items (one copy per campaign recipient
  without a login link, plus inbox replies, notices, test emails and access-check probes). Verification
  codes, admin invitations, tickets and campaign messages with a login link are sent as JSON and leave no
  copy. Received mail stays in the Inbox. Retention is set by the UC Merced Microsoft 365 records policy for
  the mailbox, not by the site.
- **Inbox views on the site.** Production has no Redis, so the site cache is a file cache on each
  container's disk (see [Environments](../deployment/environments.md#production-cache-today)). An opened
  message (headers, addresses, text and HTML body) and each list are written there unencrypted. They are
  served for at most 30 and 5 minutes, but the file stays on that container's disk until it is read again,
  removed when the cache is culled (above 2,000 entries), or the task is replaced. The site stores no other
  copy of received mail.
- **Site records.** The Email Log (`RecipientLog`) and campaign records keep recipients, subjects, status and
  the `Message-ID`; nothing deletes them. Recorded access checks, removed certificate rows (public data and
  the removal reason) and the admin history are kept until deleted; access checks and certificate rows go
  with their Graph configuration. Access tokens live only in process memory for about an hour.
- **Logs.** Graph log lines carry status, error code and request ID only. This repository sets no retention
  period on the ECS log groups, so it is whatever is configured in AWS (CloudWatch keeps logs forever by
  default). Entra sign-in logs and Purview audit records are kept for the period UC Merced's licences give.
  CloudTrail Event history keeps 90 days of management events, Secrets Manager calls included; this
  repository defines no CloudTrail trail for longer retention.
- **Credentials.** The database never holds the private key. A replaced or removed certificate's key
  version stays in the secret (Secrets Manager has no call that deletes a single version, and the task role
  may not delete the secret), but no row pins it, so the site never reads it again; it stops working for
  anyone once Entra no longer lists its certificate. Database backups contain only public certificate data.
  Earlier builds of this branch stored the key in the database, so backups of a database that ran one may
  hold it ([Open items](#open-items-before-go-live)). Destroy laptop copies once the key is installed.

## Emergency revocation

If the private key may be exposed, or the app must stop at once, do these steps in this order. Steps 1 and 2
are done by different people: start both at once and do not wait for step 1 before step 2.

1. **Entra (Cloud Systems): stop the key.** Remove the certificate from the app (**Certificates &
   secrets**, by its SHA-1 thumbprint), or disable the enterprise application (**Properties** → **Enabled
   for users to sign in** = No). From then on Entra issues no new token with that key; this is the only step
   that stops whoever holds the key. Check that the app has no client secret or federated credential.
2. **Site (superuser): stop using it, keep email working.** On the Graph configuration's page choose
   **Remove (emergency)**, type `REMOVE`, give the reason and tick **Also switch email delivery to AWS SES**.
   The current and previous certificates are marked removed, so every process refuses Graph at its next
   send without contacting AWS or Microsoft, and email moves to SES in the same step when SES is ready
   (otherwise it stays on Graph and fails until another provider is selected on Notification Delivery). The
   admin inbox falls back to the Gmail import account. The removal is recorded in the admin history with
   the reason.
3. **Exchange Online (Cloud Systems): remove the mailbox permissions.** Under the Application Access Policy
   setup OIT reported, first remove the app's Graph application permissions and their admin consent in
   Entra, or delete the enterprise application. **Never delete the
   Application Access Policy or its group while that consent exists**: the policy is all that limits the
   consented permissions, which otherwise apply to every mailbox in the tenant. Under RBAC for
   Applications, remove the app's management role assignments as Microsoft's article describes, and confirm
   with `Test-ServicePrincipalAuthorization` that no role remains.
4. **AWS (account administrator): review CloudTrail** for `itg/backend/microsoft-graph/certificate-key`:
   `GetSecretValue`, `PutSecretValue`, `UpdateSecretVersionStage`, `PutResourcePolicy` and
   `DeleteResourcePolicy` calls by any principal other than `ecsTaskRole`, or at unexpected times.

An access token that was already issued stays valid until it expires (about 60 to 90 minutes); removing
the certificate does not end it. Exchange applies access-policy changes after an hour or more and
role-assignment changes within 30 minutes to 2 hours, so step 1 is the fastest way to stop new access.

Afterwards:

- A campaign the web process was already sending when the provider changed (background jobs disabled)
  keeps the provider it started with; after step 2 its remaining recipients are recorded `failed`. With
  background jobs enabled each email reads the current provider, so queued ones go through SES.
- Re-send what failed during the window: with background jobs, use the Background Jobs retry action for
  failed and uncertain jobs; the in-process sender does not re-send failed campaign recipients.
- Create a new key pair, have OIT register it, install it ([Rotate the certificate](#rotate-the-certificate)),
  re-run the [access check](#validate-the-access-restriction), and record the incident with InfoSec.

## Limits

Microsoft's defaults for one sender mailbox and app, as published on Microsoft Learn (see [Sources](#sources)):

| Limit | Value | Applies to |
|-------|-------|------------|
| Messages per minute | 30 | Each mailbox |
| Recipients per day | 10,000 (24-hour sliding window) | Each mailbox |
| Recipients per message | Up to 1,000 (the tenant can set fewer) | Each message |
| External recipients per day | The tenant's external recipient rate limit (TERRL), set by its licences | All UC Merced mailboxes together |
| Concurrent requests | 4 | Each app and mailbox |
| Requests per 10 minutes | 10,000 | Each app and mailbox |

- **The tenant can set lower limits.** An outbound spam policy can limit the mailbox per hour and per day
  and restrict it from sending when it exceeds them; its messages then bounce with `550 5.1.8 Access denied,
  bad outbound sender`, which arrives only as non-delivery reports in the Inbox, and only a Microsoft 365
  administrator can lift the restriction. Ask Cloud Systems which policy applies
  ([Open items](#open-items-before-go-live)).
- **What a `429` means.** Microsoft documents that SMTP submissions above 30 messages per minute are rejected.
  For Graph, a `429` comes from the limits per app and mailbox: at most four requests at a time and 10,000
  per 10 minutes. Every request counts: inline sends from each web process (login codes, invitations,
  replies, ticket resends), the worker, and the admin inbox's list and message reads. The site paces
  every send and mailbox read, but does not coordinate the four-request limit.

All app email shares one mailbox, so a campaign draws on the same allowance as login codes, tickets,
invitations, and test emails. Login-code emails are capped per destination but not in total (see
[Send verification](../deployment/send-verification.md)), so a burst of code requests for many
different addresses can use the same allowance. Every email and mailbox read is paced as described under
[Campaign pacing](#campaign-pacing). When Graph throttles a request it answers `429`, `503` or `509` and the
app pauses Graph for the mailbox; watch the sender mailbox Inbox for non-delivery reports too when volume
is high.

### Campaign pacing

Every email the site sends through Graph, and every admin inbox read, goes through the delivery-rate limiter
(`apps.core.services.delivery_rates`): one schedule per sender mailbox, shared by every web process, worker
and campaign thread. Its settings are the **Email · Microsoft Graph** and **Inbox · Microsoft Graph**
delivery-rate policies (Mail → Delivery Rates), seeded from `DELIVERY_RATES` (see
[Environments](../deployment/environments.md#delivery-rates)). How Smart rate, the manual rate, the budgets and
the stops work for every channel: [Delivery rates](delivery-rates.md).

- **Rate.** Smart rate is on by default: 80 % of Exchange's 30 messages per minute, that is 24 per minute,
  slowing down when Graph throttles and speeding up again step by step. With Smart rate off the manual rate
  applies (at most 30 per minute). A burst never lets more than 30 through in any minute.
- **Lanes.** Campaigns get at most 80 % of the rate (19.2 per minute at the default, so 1,000 recipients take
  about 52 minutes) and stop at 90 % of each daily limit, so login codes, tickets, invitations, replies and
  test emails always have the rest. The limits are 10,000 recipients per rolling 24 hours, and 500 external
  and 1,000 internal recipients per rolling hour (the Standard outbound spam preset); until **Tenant limits
  confirmed** is set, campaigns also stay under 1,000 recipients a day.
- **`Retry-After`.** A `429`, `503` or `509` from Graph pauses every Graph request for that mailbox (sends
  and reads) for the `Retry-After` value (delta-seconds or an HTTP date, capped at
  `GRAPH_MAX_RETRY_AFTER_SECONDS`), or for a backoff when there is none. A busy token endpoint pauses Graph
  the same way; refused credentials, a `403`/`404` on a send and a full mailbox (`507`) stop Graph sending
  until the configuration is saved again or a timed probe succeeds.
- **Queued email.** The background worker claims tickets and security notices before campaign recipients,
  and leaves campaign jobs unclaimed while the campaign lane waits for its next slot. A job held back by the
  limiter runs again at its slot without using up an attempt.
- **Email sent from a request** (login codes, invitations, replies, the test email, the **Send ticket email
  now** button, a member's own ticket resend) waits up to 10 seconds for its slot; beyond that it is not
  sent, and a login code tells the person to try again in about N seconds.
- **Without the worker** the web server sends a campaign itself, waiting for each slot (up to 15 minutes).
  A longer hold, such as a daily limit or a Graph stop, pauses the remaining recipients and the campaign
  ends partial; the **Resume paused recipients** action on the Email Campaigns list sends exactly those
  later (queued for the worker when background jobs are enabled).
- **Confirmation page.** Before a campaign is sent, the confirmation page shows the campaign rate, the
  expected duration, the daily limit and the campaign share of it, and warns when the campaign has more
  recipients than that share. It does not block the send.
- **Bulk ticket actions.** Sending ticket emails from one request (**Send All Tickets**, and the
  multi-select **Resend ticket email** action) and resending invitations in bulk are refused above what one
  request sends at the current rate in 25 seconds (13 at the default Graph rate). Select fewer.
- **[CONFIRM LIVE]** Not observed against the tenant: the format of `Retry-After` on Outlook `429`s (both forms
  are parsed); whether going over a sending limit returns an error or a `202` followed by a non-delivery report
  (only an error slows the limiter); the outbound spam policy that applies to `i2g@ucmerced.edu` (tick **Tenant
  limits confirmed** on the Graph card, and adjust the hourly limits, only once Cloud Systems has stated it); and
  whether staff also send from the mailbox in Outlook, which the 0.8 headroom assumes.

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
| `401` for a token issued for this send | Transient | `Microsoft Graph rejected the access token; it will be refreshed.` | The grant itself is refused, so Graph sending also stops ("refused the credentials" on Mail → Delivery Rates) until the Graph configuration is saved or the timed probe succeeds: queued mail waits instead of failing one message at a time. Check **Tenant ID**, **Client ID**, the installed certificate and the app's Mail.Send permission. |
| `403` | Permanent | `Microsoft Graph rejected the request (ErrorAccessDenied).` or `(ErrorSendAsDenied)` | The app may not send as this mailbox or address: the mailbox is outside the Exchange restriction (the access policy's group or the management scope), the permission was removed, a change has not applied yet (more than an hour), or **From Email** is not the mailbox or an address it may send as. The cached token is dropped, so the next send picks up Entra permission changes; Exchange restriction changes apply on Exchange's schedule. Never widen the Entra grant to fix it. |
| `404` | Permanent | `Microsoft Graph rejected the request (MailboxNotEnabledForRESTAPI).` or `(ResourceNotFound)` | **Sender Mailbox** (or **From Email**, when blank) is not an Exchange Online mailbox, or is misspelled. Use the mailbox's primary address. |
| `400` | Permanent | `Microsoft Graph rejected the request (<code>).` | Graph refused the request or the MIME content, for example an invalid recipient. The code names the problem. |
| `413` | Permanent | `Microsoft Graph rejected the request (<code>).` | The message is too large, usually attachments. The request-size limit for MIME `sendMail` is not documented in the pages under [Sources](#sources). |
| Other `4xx` | Permanent | `Microsoft Graph rejected the request (<code>).` | Look the code up on Microsoft's Graph errors page. |
| `408`, `429`, `503` | Transient | `Microsoft Graph temporarily rejected the request.` | Throttled or briefly unavailable. The `Retry-After` value (capped at 3,600 seconds) delays the background worker's next attempt; see [Campaign pacing](#campaign-pacing). A recurring `429` usually means more than four requests at once for the mailbox ([Limits](#limits)): spread out bulk actions and campaigns; the limiter already pauses Graph for the mailbox after each one. |
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
| `invalid_client`, `AADSTS700027` | Permanent | `Microsoft rejected the Graph credentials (invalid_client AADSTS700027).` | The assertion's signature or key is not recognised: the certificate in the admin is not (or no longer) uploaded to this app in Entra. Compare the SHA-1 thumbprint shown in the admin with the one in Entra. |
| `unauthorized_client`, `AADSTS700016` | Permanent | `Microsoft rejected the Graph credentials (unauthorized_client AADSTS700016).` | No app with this **Client ID** exists in this tenant. Check **Client ID** and **Tenant ID**. |
| Any other rejection (an unknown tenant, a disabled app `AADSTS7000112`, `invalid_scope`, other `4xx`) | Permanent | `Microsoft rejected the Graph credentials (<error> AADSTS<number>).` | Look the AADSTS number up in Microsoft's error-code reference. |
| `408`, `429`, `5xx` | Transient | `Microsoft identity platform is temporarily unavailable.` | Retried later by the background worker (`Retry-After`, when sent, delays that retry); without the worker the send fails once. |
| Cannot connect | Transient | `Microsoft identity platform could not be reached.` | Outbound HTTPS to `login.microsoftonline.com` is blocked or the network is down. |
| No answer, or reset | Transient | `Microsoft identity platform did not answer.` | Safe to repeat. |
| `200` with an unreadable body | Transient | `Microsoft identity platform returned an unreadable response.` | Safe to repeat. |
| Certificate verification fails | Permanent | `TLS verification of the Microsoft identity platform failed.` | TLS interception, or an outdated CA bundle in the container. |

### Refused before any request is made

| Situation | Class | Message recorded | Cause and action |
|-----------|-------|------------------|------------------|
| The sending mailbox or **From Email** is not in the mailbox scope with send permission | Permanent | `Microsoft Graph may not send as <mailbox>: it is not in the configured mailbox scope with that permission.` | Add the mailbox to the scope (and to the Exchange restriction, after InfoSec review) or fix **Sender Mailbox** / **From Email**. |
| No usable current certificate (none, removed, expired, not valid yet, or tested for another app) | Permanent | `No usable Microsoft Graph certificate is installed.` or `Active Microsoft Graph provider configuration is missing or invalid.` | Install a certificate; check its validity in the admin. |
| The pinned key cannot be read from the credential store | Transient (throttling, outage, timeout, or the task role's credentials not fetched in time: `NoCredentialsError`, `CredentialRetrievalError`, `MetadataRetrievalError`) or Permanent | `The Microsoft Graph private key could not be read: <fixed text> (<AWS error code>)` | Permanent codes such as `AccessDeniedException` or `ResourceNotFoundException` mean the task role, the resource policy or the secret is wrong; reinstall the certificate if its version is gone. |
| The stored key does not match the installed certificate | Permanent | `The Microsoft Graph private key could not be read: The stored private key does not match the installed certificate.` | Reinstall the certificate with its own private key. |
| The certificate private key cannot be used to sign | Permanent | `The Microsoft Graph certificate private key could not be used.` | Reinstall the certificate and private key. |
| A Bcc recipient is present on a MIME message | Permanent | `Microsoft Graph does not support Bcc recipients.` | Send separate messages instead. |
| The MIME or JSON message cannot be built | Permanent | `The email could not be composed for Microsoft Graph.` | Fix the message. Composition errors raised by the builders keep their own message, for example `Email has no recipients.`, `An email recipient address is invalid.` or `An email header is malformed.` |
| A request outside the allowlist | Permanent | `The site does not make this Microsoft Graph request.` | A code defect, or a mailbox value whose encoding is refused (an encoded `.`, `/` or `\`). Nothing was sent. |
| The provider was built with a malformed tenant ID, client ID, mailbox or key pointer | Permanent | `Microsoft Graph configuration is invalid.` | Only reachable for rows written outside the admin, which validates these; fix and re-save the configuration in the admin. |
| No active, complete, well-formed Graph configuration | Permanent | `Active Microsoft Graph provider configuration is missing or invalid.` | Tick **Active**, fill in **Tenant ID** and **Client ID**, install a certificate, and add at least one mailbox scope row. An expired certificate, or a row saved outside the admin with a malformed tenant ID, client ID, or sender mailbox, counts as not configured; fix and re-save it in the admin. |
| No active email configuration | Permanent | `No active email service configuration exists.` | Tick **Active** under **Email Sender**. |

## Troubleshooting checklist

1. **Test email fails with "Microsoft rejected the Graph credentials".** Check **Tenant ID** and
   **Client ID** against the app's Overview page, and that the certificate shown in the admin (SHA-1
   thumbprint, expiry) is uploaded to that app under **Certificates & secrets**.
2. **Test email fails with `(ErrorAccessDenied)` or `(ErrorSendAsDenied)` (HTTP 403).** Ask Cloud Systems
   for `Test-ApplicationAccessPolicy -Identity <sender mailbox> -AppId <client-id>` (`Granted`), or under
   RBAC for Applications `Test-ServicePrincipalAuthorization` (`InScope` True). After a change, wait at least
   an hour (up to 2 hours for role assignments). Check that **From Email** is the sender mailbox or an address
   it may send as.
3. **Test email fails with `(MailboxNotEnabledForRESTAPI)` or `(ResourceNotFound)` (HTTP 404).** Check the
   **Sender Mailbox** spelling, and confirm in the Exchange admin center that it is an Exchange Online
   mailbox rather than an on-premises one.
4. **"Test email sent", but nothing arrives.** HTTP 202 only means queued. Look in the sender mailbox:
   Sent Items should hold a copy, and the Inbox may hold a non-delivery report with the reason. Check
   the recipient's junk folder.
5. **All email suddenly fails.** The certificate may have expired (the configuration then counts as not
   configured) or been removed in Entra (`AADSTS700027`), the key may be unreadable (`The Microsoft Graph
   private key could not be read`), the mailbox may be full (`507`), or Exchange may have restricted it
   from sending (non-delivery reports with `550 5.1.8`; Cloud Systems must lift it). Check **Certificates &
   secrets** in Entra, `verify_service_configs`, the Inbox and the mailbox size.
6. **Frequent `429` or "temporarily rejected".** Spread out bulk actions, stop other tools that use the
   same app or mailbox, keep Smart rate on (or lower the manual rate) for **Email · Microsoft Graph** under
   Mail → Delivery Rates, and see [Limits](#limits).
7. **Campaign recipients marked `uncertain`, or `failed` after a Graph error.** Read the job's **Last
   error** (Admin → Background Jobs) and the [error reference](#error-reference); check Sent Items before
   sending again.
8. **Install refused.** The page names the reason: a key that does not match, a key shorter than 2048 bits,
   a certificate that is not valid now, an unexpected SHA-1 thumbprint, or Entra's answer
   ([Install the certificate](#2-install-the-certificate)). `The private key could not be stored` with an
   AWS error code means the identity stack is not deployed or the task role lacks the grant.
9. **Confirm the stored settings.** Run `python manage.py verify_service_configs --strict`.
10. **Ask Microsoft for help.** Each rejected `sendMail` writes one backend log line at WARNING level,
    `Microsoft Graph sendMail was not accepted: status=<status> code=<code> request_id=<id>` (CloudWatch
    Logs in production). Quote the request ID and the time. If a message has no code in parentheses,
    `status=<status>` in that line tells the cases apart. An unexpected error after a send began writes
    `Unexpected <ExceptionType> while sending through Microsoft Graph` at ERROR level instead.

### First live check

After a new setup or a credential change:

1. Send a test email to an external mailbox you can open. Confirm it arrives, shows the configured
   **From Name** and **From Email**, and leaves a copy in the sender mailbox's Sent Items.
2. Request a sign-in code for your own account. Confirm it arrives with the same From and that **no** copy
   is in Sent Items (JSON `sendMail` with `saveToSentItems: false`).
3. Send a small campaign without `{{login_link}}` to yourself. In the received message's headers confirm
   `List-Unsubscribe` and `List-Unsubscribe-Post`, and that the `Message-ID` matches the provider message
   ID in the Email Log. Then send one that uses `{{login_link}}`: confirm the link works, the footer
   unsubscribe link is there, and **no** copy is in Sent Items.
4. Send yourself a ticket email. Confirm the inline barcode image displays and the calendar file is
   attached, that a subject or name with accented characters displays correctly, and that no copy is in
   Sent Items. Confirm the received message shows a sent date (the app does not write a `Date` header;
   Exchange is expected to add one).
5. Open the Inbox in **Mail → Inbox** as a superuser and as a Mail-only staff user; only the superuser sees
   the **Sent** tab.
6. In a non-production environment, install a throwaway certificate that is not registered on the app on an
   inactive configuration and confirm its Entra check reads not trusted (`AADSTS700027`).
7. Confirm the small campaign completed without `429` responses.
8. After a credential change, run the access check again: evidence recorded with another certificate does
   not count for the go-live gate.

## Sources

- [`sendMail` API reference](https://learn.microsoft.com/en-us/graph/api/user-sendmail): the JSON and MIME formats, `saveToSentItems`, custom `x-` headers (`internetMessageHeaders`), the `202` response, and the Sent Items copy of a MIME send.
- [Things to know about sending mail](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail)
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference): `Mail.Send`, `Mail.Read`, and `Mail.ReadWrite` ("create, read, update, and delete mail … Does not include permission to send mail").
- [Limit application permissions to specific Exchange Online mailboxes](https://learn.microsoft.com/en-us/graph/auth-limit-mailbox-access): Application Access Policies, `Test-ApplicationAccessPolicy`, the `Access to OData is disabled` error, that application permissions reach all mailboxes by default, and that policy changes can take more than an hour to apply.
- [RBAC for Applications in Exchange Online](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac): scoping an app to specific mailboxes, the `Application Mail.Send` / `Application Mail.Read` roles, why tenant-wide Entra grants must be removed, and the move from Application Access Policies.
- [Access tokens in the Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens): the `roles` claim, and that apps decode tokens for validation and debugging only.
- [Microsoft identity platform certificate credentials](https://learn.microsoft.com/en-us/entra/identity-platform/certificate-credentials): the client assertion format (`PS256`, `x5t#S256`, claims).
- [OAuth 2.0 client credentials flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)
- [Get MIME content of a message](https://learn.microsoft.com/en-us/graph/outlook-get-mime-message) and [List messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages): the `Mail.Read` calls the admin inbox makes.
- [Microsoft Graph throttling limits](https://learn.microsoft.com/en-us/graph/throttling-limits): four concurrent requests and 10,000 requests per 10 minutes per app and mailbox.
- [Microsoft Graph error responses](https://learn.microsoft.com/en-us/graph/errors)
- [Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits): messages per minute, recipients per day and per message, and the tenant external recipient rate limit.
- [Email non-delivery reports and SMTP errors in Exchange Online](https://learn.microsoft.com/en-us/troubleshoot/exchange/email-delivery/ndr/non-delivery-reports-in-exchange-online): `550 5.1.8` and the other NDR codes.
- [Microsoft Entra authentication and authorization error codes](https://learn.microsoft.com/en-us/entra/identity-platform/reference-error-codes): the AADSTS numbers.
- [AWS Secrets Manager: secret versions](https://docs.aws.amazon.com/secretsmanager/latest/userguide/whats-in-a-secret.html) and [resource-based policies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_resource-policies.html): staging labels, `AWSCURRENT`, and the resource policy on the key secret.

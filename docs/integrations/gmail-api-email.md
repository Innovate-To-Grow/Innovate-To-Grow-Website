# Gmail API email

The Gmail API provider sends the site's email as a Google Workspace account (by default `i2g@g.ucmerced.edu`)
through a Google Cloud service account with **domain-wide delegation for exactly one scope,
`https://www.googleapis.com/auth/gmail.send`**. It is selected under **Mail → Notification Delivery** like SES, SMTP
or Microsoft Graph; there is no per-message routing and no automatic failover.

Code: `src/apps/core/services/email/gmail/` (provider, assertion, token exchange, transport, errors, key handling and
the access check), `src/apps/core/models/base/service_credentials/gmail_api.py` (`GmailApiProviderConfig`,
`GmailApiSubject`), `src/apps/core/admin/service_credentials/gmail_api*.py` (admin pages), and
`src/apps/core/services/delivery_rates/adapters/gmail_api.py` (rate signals).

## How it works

- **Who it sends as.** The site impersonates only the accounts on the config's **account allow-list**, and always
  sends **From** the impersonated account: the From email on Notification Delivery must be on the list. The list is
  checked before any key read or request to Google, on every send, so removing an account takes effect at once.
- **Authentication.** For each account the site signs a short-lived JWT assertion (RS256; `iss` the service
  account, `sub` the account, `scope` gmail.send, `aud` `https://oauth2.googleapis.com/token`) with the service
  account's key and exchanges it at `https://oauth2.googleapis.com/token`. Access tokens are cached in process
  memory only (keyed by service account, key ID, pinned key version and account), never in the database, the shared
  cache or logs. A cache hit never reads the key.
- **Sending.** The raw MIME is uploaded to
  `POST https://gmail.googleapis.com/upload/gmail/v1/users/me/messages/send?uploadType=media` as `message/rfc822`.
  The transport makes no other request, follows no redirect, ignores proxy variables and reads at most
  `GMAIL_API["max_response_bytes"]` of an answer. Bcc, `Sender`, `Return-Path` and `Resent-*` headers, more
  recipients than the config allows (Google: 500) and larger messages (Google: 25 MB before encoding; the site
  checks the encoded size) are refused before any token is requested. Gmail's `200` only means it accepted the
  message: near a daily limit Google may still drop it, which is why the delivery-rate budgets stop below the
  limits.
- **The key.** It never touches the database: the config keeps the store reference, the pinned version and the
  key's public facts (key ID, service account, numeric client ID, project). In production the key is the Secrets
  Manager secret `itg/backend/gmail-api/service-account-key` (created empty and retained by
  `aws/cicd/identity-stack.json`; the ECS task role may read, describe and add versions to it, and nothing else).
- **Rates.** Channel `gmail_api_send` on **Mail → Delivery Rates**, Smart rate on: 60 messages/min ceiling, 2,000
  messages, 3,000 recipients and 2,000 external recipients per rolling 24 hours, with a 0.9 budget headroom and a 25 %
  reserve for sign-in codes and tickets. The limits include mail people send from the account in Gmail, which the
  site cannot see. Values and sources: `config/settings/base/integrations/delivery_rates/channels.py`; how Smart rate
  and the budgets work: [Delivery rates](delivery-rates.md).

Items marked **[CONFIRM LIVE]** are taken from Google's documentation and were not observed: nothing in this change
was sent to Google (the tests use mocked HTTP).

## Set up

### Google Cloud owner

1. Use a **dedicated project** with few editors ("Ensure that service accounts with domain-wide delegation are
   hosted in dedicated Google Cloud projects").
2. Enable the Gmail API: `gcloud services enable gmail.googleapis.com --project=PROJECT_ID`.
3. Create a service account with **no** project IAM roles. Grant nobody `iam.serviceAccountTokenCreator` or
   `iam.serviceAccountKeyAdmin` on it.
4. Create one key: `gcloud iam service-accounts keys create key.json --iam-account=SA_NAME@PROJECT_ID.iam.gserviceaccount.com`
   (a console-created key file works too). Keys never expire by default: put rotation in the calendar or set an
   organization policy on key expiry.
5. Google recommends organization policies that "restrict key creation and upload for service accounts with
   domain-wide delegation". **[CONFIRM LIVE]** whether UC Merced's policy allows creating this key at all, its
   key-expiry policy, and who owns the project.

### Workspace super admin

1. Admin console → Security → Access and data control → API controls → **Manage Domain Wide Delegation** → Add new.
2. Client ID: the **numeric client ID** shown on the site's Gmail API config page (authorizing by the service
   account's email address instead is a documented cause of `unauthorized_client`).
3. OAuth scopes: **exactly** `https://www.googleapis.com/auth/gmail.send`. Use "View details" afterwards to confirm
   that only that scope is listed. With Multi-party approval, a second super admin approves.
4. Changes "can take up to 24 hours". Confirm that the sending account has Gmail enabled, and tell I2G the Workspace
   **primary domain** (set it as the Gmail API channel's internal domain on Mail → Delivery Rates; blank counts every
   recipient as external). The field accepts only the domain of an account on a Gmail API allow-list or a parent
   domain of it (for `i2g@g.ucmerced.edu`: `g.ucmerced.edu` or `ucmerced.edu`), or the deployer's
   `DELIVERY_RATES` seed, so naming it cannot lift Google's external-recipient limit for unrelated domains.
   **[CONFIRM LIVE]** UC Merced's primary domain: Google counts aliases and alternate domains as external.

### Site admin with the Core app

The Gmail API configuration's page (`/admin/core/gmailapiproviderconfig/`, Site Settings → Service Credentials →
Gmail API) needs the **Core** app; superusers always have it.

1. **Core → Gmail API Provider Configs → Add**: a name, then add the From address to the **account allow-list**.
2. **Install key**: paste or upload `key.json`. The site checks it in memory, asks Google for a gmail.send token as
   the From address with it, stores it and pins it. A first key may be installed while delegation is still pending
   (`unauthorized_client` / `access_denied`); any other refusal stores nothing. Delete `key.json` afterwards.
   **[CONFIRM LIVE]** that Google checks the assertion's signature before delegation, so that a pending-delegation
   answer still proves the key is genuine.
3. **Run access check** (or `manage.py verify_gmail_access`). It must show the pinned key readable, a token for
   every listed account, an unlisted address refused by the site with no request to Google, and every broader scope
   refused by Google (a canary set: full Gmail, read, modify, compose, insert, metadata, labels, settings,
   `cloud-platform`, Directory, Drive, Calendar). Checks 1-5 passing record the evidence; the optional probe sends
   one message from each account to itself.
4. Activate the config, then select **Gmail API** on Mail → Notification Delivery. Switching email to the Gmail API,
   or changing its From address there, needs that evidence for the installed key.

## InfoSec note

**Reach.** Domain-wide delegation with gmail.send lets whoever holds the service-account key send mail **as any user
in the UC Merced Workspace domain**, not only as the accounts on the site's allow-list. Google: "With domain-wide
delegation, the app has access to the data belonging to all of your users", and "OAuth scopes don't restrict which
users the service account can impersonate". gmail.send cannot read mail ("Send email on your behalf").

**Mitigations, and what each one covers:**

1. **The site's allow-list, with From = the impersonated account.** Checked before any key read or token request
   and proven by the access check. It protects against site bugs and misconfiguration only, **not** against a
   compromised task, task role or key.
2. **Exactly one delegated scope.** Proven by the access check's broader-scope canary and by "View details" in the
   Admin console. The canary cannot enumerate every scope Google offers.
3. **The key lives only in Secrets Manager**: a pinned version, a narrow task-role grant and a resource policy; it is
   never shown, logged or cached, and its config is on the safe-ORM (CLI) denylist. The ECS task role is still a
   single point of compromise for domain-wide send-as.
4. **A dedicated Google Cloud project** with few editors, a key-creation organization policy, and no
   `iam.serviceAccountTokenCreator` or `iam.serviceAccountKeyAdmin` grants.
5. **Revocation** ([below](#revocation-and-compromise)) and a periodic review: Google recommends "a regular review of
   service accounts and deleting any accounts no longer in use".

**Per-user restriction.** Google's delegation pages describe no organizational-unit or per-user restriction for a
delegation client. **[CONFIRM LIVE]** with the UC Merced Workspace admin whether any OU or context-aware control
applies, and which audit log shows mail sent through the client.

**Alternatives (recorded, not built; domain-wide delegation with a key was chosen):**

- **OAuth consent by `i2g@` only.** Google: "Avoid using domain-wide delegation if you can accomplish your task
  directly using a service account or with OAuth consent." A refresh token that `i2g@` grants for gmail.send reaches
  only that one mailbox, so a compromise could not impersonate other users. It is still a long-lived secret tied to
  the account. This is the narrowest option.
- **Keyless signing.** "Using service account keys is not necessary to perform domain-wide delegation. Use the
  signJwt API instead." With Workload Identity Federation from the ECS task role no key would exist, but the reach is
  the same (any user).

## Rotation

1. Create the new key in Google Cloud (up to 10 keys per service account; wait about a minute before using a new
   key).
2. **Install key** with it. For the same service account Google must issue a token before anything is written; the
   old key's stored version stays as it was until then. Every install clears the evidence.
3. **Run access check** again (needed before the next go-live or From change; sends keep working meanwhile, and
   `verify_service_configs --strict` fails until it passes).
4. Disable the old key (`gcloud iam service-accounts keys disable OLD_KEY_ID --iam-account=…`), and delete it after a
   healthy day. Delegation is bound to the client ID, not the key, so it is unaffected.

## Revocation and compromise

Whoever holds the key can mint gmail.send tokens for **any user in the Workspace domain**: Google offers no per-user
restriction for domain-wide delegation, so the site's allow-list protects only against site errors. Disabling or
deleting a key does not revoke tokens already issued (they last up to an hour). In order:

1. Workspace super admin deletes the delegation client ("Applications that depend on the client authorization will
   immediately stop working"; Multi-party approval can delay this).
2. Google Cloud: disable the service account, then delete the key.
3. Site: **Remove key** on the config page (it can switch email to AWS SES in the same step), then review CloudTrail
   `GetSecretValue` / `PutSecretValue` events on the secret and the Workspace audit logs.

## Sent folder and credential mail

Gmail always files a copy of what it sends in the account's **Sent** folder; the gmail.send scope cannot remove it.
Mail that carries a credential (sign-in codes, login links, admin invitations, tickets, campaign messages with a
`{{ login_link }}`) is tagged `X-I2G-Mail-Class: credential` (callers cannot set this header), and:

- the admin inbox's **Sent** view and **Import from Gmail** (Gmail IMAP, which reads only Sent) never list, open,
  snippet or cache tagged messages (the IMAP search leaves them out and anything that still comes back is dropped).
  The header is not authenticated (anyone can add it to mail they send the account), so it is honoured only in Sent,
  which holds only the account's own outgoing mail; received mail is listed as before, tagged or not;
- while email is sent through the Gmail API, or the Gmail import account is on an allow-list, the inbox's **Sent**
  folder is shown to staff with the **Mail** app only (anyone who can open Mail → Inbox), with tagged mail left out
  as above;
- **Mail With Codes or Login Links = Refuse** on the config makes such mail fail with this provider instead (it then
  blocks sign-in codes if the Gmail API is the only provider).

Only people trusted like Core-app admins should be able to sign in to the sending account directly (2-Step
Verification, no shared password). How long Sent copies are kept (for example a Vault retention rule) is a
records-policy decision for UC Merced. **[CONFIRM LIVE]** that the header survives in the Sent copy.

## Operations

- **Standby provider.** Keep SES configured as a standby. When Google's daily sending limit trips ("(Mail sending)"
  `429`), the Gmail API channel stops on every lane and sign-in codes can stop for up to 24 hours; the step is to
  switch Notification Delivery to SES. Providers never fall back by themselves. Switching back to the Gmail API later
  needs a passed access check for the installed key; the earlier one still counts unless the key was replaced since.
- **Limits are shared with people.** Google's daily limits are per account and include mail sent from it by hand in
  Gmail. The channel stops at 90 % of each limit, and campaigns at 75 % of that, which is the only protection: the site
  cannot see the manual use. Lower the limits on **Mail → Delivery Rates** if people send from the account a lot.
- **Monitoring.** Suggested CloudWatch metric filters on the backend and worker logs: `Gmail API send was not
  accepted` (logged with the status and Google's reason code) and `Google rejected the Gmail API credentials` (in the
  logged delivery error). CloudTrail alerts on any `GetSecretValue` or `PutSecretValue` for the key's secret by a
  principal other than `ecsTaskRole` (the resource policy denies them, so each is an attempt). A Workspace alert for
  mail sent through this client by an account not on the allow-list, once the log is known (above). The live state is
  on the **Email · Gmail API** card.
- **`verify_service_configs --strict`** fails while the Gmail API is selected and the allow-list is empty, does not
  contain the From address, or the installed key has no passed access check. Nothing schedules it today; running it
  on a schedule is a decision for operations.

## Errors and rate signals

Google's answers become classified delivery errors with a rate signal (`delivery_rates.adapters.gmail_api`; patterns
in `DELIVERY_RATES["signals"]["gmail_api"]`). Google's free text is matched, never stored or shown.

| Answer | Error | Rate effect |
|--------|-------|-------------|
| 403 `rateLimitExceeded` / `userRateLimitExceeded`, 408, other 429 | Transient | Cooldown (Retry-After or backoff) |
| 429 "Too many concurrent requests" | Transient | 1 s cooldown |
| 429 "User-rate limit exceeded (Mail sending)" | Transient | Daily-sending breaker on every lane, probed from 15 minutes up to 6 hours, or at the retry time Google names |
| 429 "User-rate limit exceeded" (bandwidth) | Transient | Bandwidth breaker for an hour |
| 403 `dailyLimitExceeded` (project quota) | Transient | Breaker, re-checked after an hour |
| 401 with a cached token | Transient | Token dropped and refreshed |
| 401 with a fresh token, other 403 | Permanent | Auth breaker until the config is saved |
| 403 `domainPolicy`, 400 `failedPrecondition`, 404 | Permanent | Permission breaker until the config is saved |
| 400 `badRequest` / `invalidArgument`, 413 | Permanent | This message only |
| 5xx, a lost response | Uncertain (no idempotency key, so never assumed "not sent") | Usage stays counted |
| Token: `unauthorized_client`, `access_denied`, `invalid_grant`, `disabled_client`, … | Permanent, with the cause | Auth breaker |
| Token endpoint busy or unreachable, key store busy | Transient | Pause and back off |

## Settings

`GMAIL_API` (`config/settings/base/integrations/gmail_api/`, overridable with `GMAIL_API_OVERRIDES`): request
timeout, response cap, recipients and size ceilings (also the config fields' seeds and ceilings), the upload
endpoint's maximum, assertion and token lifetimes, key-file size and RSA key size, and the key-test and access-check
timeouts. See [Environments](../deployment/environments.md#gmail-api-email).

## To confirm with Google and UC Merced [CONFIRM LIVE]

None of these was observed; each is either undocumented or depends on UC Merced's tenant.

1. The format of the "retry time" in a "(Mail sending)" `429`, and whether Google sends a `Retry-After` header.
2. Whether Gmail keeps the supplied `Message-ID` (check the first live send with `rfc822msgid:` in the account).
3. Whether Google checks the assertion's signature before delegation, so that `unauthorized_client` on a first
   install proves the key is genuine.
4. The HTTP status Google uses for `unauthorized_client` (400 or 401); the site classifies by the code either way.
5. The `messages.send` 400 and 403 reasons for "Gmail not enabled", insufficient scope and "API disabled".
6. Whether `sub` accepts a user's alias, or only the primary address (the site sends only as listed addresses).
7. Whether Gmail IMAP supports `SEARCH HEADER X-I2G-Mail-Class credential` (the post-fetch filter covers it either
   way), and whether the header survives in the Sent copy.
8. UC Merced's Workspace primary domain, its key-creation and key-expiry organization policies, and who owns the
   project.
9. Whether the Workspace offers any OU or user restriction for a delegation client, and which audit log shows mail
   sent through it.
10. Whether people also send from `i2g@` in Gmail (shared limits and Sent folder), and who can sign in to it.
11. Whether the Gmail API will be the only provider. If it is, or if InfoSec rejects Sent copies of credential mail,
    such mail needs a provider that keeps no copy (SES); the site has one active provider today.
12. Which per-minute Gmail API quota the project gets (6,000 units per user for a new project; a project that used
    the API before Google's 2026 change may keep more).

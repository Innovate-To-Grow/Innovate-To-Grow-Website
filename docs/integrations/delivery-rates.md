# Delivery rates (Smart rate and manual rate)

Every message the site sends and every inbox session it opens goes through one limiter,
`apps.core.services.delivery_rates`. It paces seven **delivery channels** with the same rules, the same policy model
and the same settings card on **Mail → Delivery Operations → Delivery Rates**. Each channel has a **manual rate** and
a **Smart rate** switch. Smart rate is on for every channel by default.

Items marked **[CONFIRM LIVE]** come from provider documentation or from reasoning about it. Nothing in this change
was tried against AWS, Microsoft or Google: the tests use stubs (botocore `Stubber`, mocked HTTP).

## Channels

| Channel | Card | Unit | Identity (state key) | Cooldown group | Costs: pace / daily budget |
|---------|------|------|----------------------|----------------|----------------------------|
| `graph_send` | Email · Microsoft Graph | messages/min | sender mailbox | `graph:<mailbox>` | 1 per message / recipients (To, Cc, Bcc), external ones also counted separately |
| `graph_read` | Inbox · Microsoft Graph | requests/min | mailbox | `graph:<mailbox>` (shared with sends) | 1 per GET / none |
| `ses_send` | Email · Amazon SES | recipients/sec | `<AWS config id>:<region>` | `ses:<region>` | recipients / recipients (SES counts every recipient) |
| `smtp_send` | Email · SMTP (Gmail SMTP and the relay included) | messages/min | `host:port:username` | the identity | 1 per message / recipients, plus 1 message |
| `gmail_imap` | Inbox · Gmail (admin inbox and Import from Gmail) | sessions/min | `imap host:username` | `gmail:<username>` | 1 per uncached login session / none |
| `gmail_api_send` | Email · Gmail API | messages/min | the From account (lower case) | `gmail_api:<account>` (not shared with IMAP) | 1 per message / recipients (Gmail refuses Bcc), external recipients and 1 message |
| `sms_send` | SMS · AWS End User Messaging | messages/sec, plus message parts/sec | `<region>:<origination>` | `sms:<region>` | 1 message and `sms_parts(body)` parts / 1 message |

- Settings (policy) are per channel; state is per channel **and identity**. A new mailbox, SMTP host, AWS account,
  Region or number starts with fresh state.
- A cooldown applies to the whole cooldown group. Microsoft limits Outlook "to each app ID and mailbox
  combination", so a Graph `429` on a read also pauses that mailbox's sends. The SMS `SendTextMessage` quota is per
  account and Region, so an SMS throttle pauses every number in the Region.
- Only the email channel of the provider selected under **Mail → Notification Delivery** carries mail. The other
  email cards stay editable under **Not in use**.

## Smart rate or manual rate

The page shows these help texts (`apps/core/models/base/delivery_rates.py`):

> **Smart rate.** Adjusts the rate automatically to actual conditions. It uses the limit the provider reports (where
> it reports one), slows down as soon as the provider throttles or pushes back, then speeds up again step by step,
> never above the provider limit. While Smart rate is on it takes priority over the manual rate; the manual rate is
> kept and is used again when you turn Smart rate off.

> **Manual rate.** Fixed rate used while Smart rate is off. It cannot be set above the provider limit (Advanced).
> Pauses the provider explicitly asks for, and daily limits, still apply.

The manual rate is always posted, validated and stored, also while Smart rate is on (the field is then read-only
on the page). It is never discarded.

### Precedence

The rule has one implementation, `rules/policy.py: effective_rate(policy, state, spec, now)`. The limiter, the status
lines, the send estimates and the inline batch limit all call it.

```
bound B   = the smallest of: the limit the provider last reported for this identity,
            the documented limit (DELIVERY_RATES), and the operator's "Provider rate limit" (Advanced)
            else the channel's fallback_rate, shown as "limit unknown"
Smart on  : rate = min(B × headroom × factor(now), ⌊B⌋)    the manual rate is never read
Smart off : rate = manual rate, capped at min(B, ⌊B⌋) only when B is a known limit (never at the fallback)
Both      : burst k = min(burst − 1, ⌊B⌋ − rate) in the channel's unit, so no window of one unit
            (a second or a minute) holds more than ⌊B⌋ requests
            cooldowns, breakers and daily budgets apply in both modes
            campaigns (bulk lane) use at most bulk_share × rate
SMS       : one message every max(1 / message rate, parts / parts rate);
            Smart scales both rates, the manual rate sets only the message rate
```

- **Whole requests.** A window holds whole requests, so under a fractional bound of at least one per window the pace
  is at most ⌊B⌋: a 14.5 recipients/sec limit sends at most 14 in any second, with Smart rate at full speed or a
  manual rate of 14.5 alike (the status line then says the manual rate is capped).
- **Carried-over SES limit.** A provider limit migration 0036 copied from the old campaign send rate counts only until
  AWS reports a limit for the account; from then on the reported one replaces it (below).
- **Last-known.** The limit a provider reported is used whatever its age. A failed read keeps it and adds a warning
  to the status line ("AWS limits last read 26 h ago (AccessDenied: ses:GetAccount); using the last known 14
  recipients/sec"). The fallback applies only while the provider has never answered for that identity.
- **Never above the provider limit.** The factor and the headroom are at most 1, B is the minimum of every known
  limit, and the burst is clipped, so Smart rate never sends faster than any limit it knows. Staff can lower a limit
  under Advanced but never raise B above what the provider reports or documents.
- **Switching.** Turning Smart rate on starts it afresh (factor 1, or 0.5 while B is only the fallback). Turning it
  off needs nothing. A cooldown or stop the provider caused survives either switch.
- **Ceilings.** A documented limit in `DELIVERY_RATES` is also a ceiling. The model's `clean()` refuses a manual
  rate above the operator's or the documented limit, and any documented limit raised above its settings value ("At
  most X (documented): it can be lowered here, not raised."). At runtime the settings value is applied again, so a
  deployer who lowers a ceiling with `DELIVERY_RATES_OVERRIDES` also caps rows stored earlier.

### How Smart rate reacts

| Event | Effect |
|-------|--------|
| The provider throttles (`429`, `ThrottlingException`, `421 4.7.0`, …) | Cooldown for the whole group: the provider's `Retry-After` (seconds or an HTTP date, capped at `controller.retry_after_max_seconds`, 3,600 s; Microsoft Graph also at `GRAPH_MAX_RETRY_AFTER_SECONDS`, the smaller applying), else a backoff that doubles from the channel's `backoff_initial_seconds` to `backoff_max_seconds` (±20 % jitter). No burst follows a cooldown. With Smart rate on, the factor is also halved (`decrease_factor` 0.5), once per episode, never below `floor` 0.25 |
| Pushback on a non-throttle answer (Graph `ApplicationThrottled`) | The same pause; the message counts as possibly sent |
| An unclear outcome (5xx, lost response) | No speed-up credit for this interval; the usage stays counted |
| Success | Throttle count reset; after every `recovery_interval_seconds` (600 s for Graph, SMTP, IMAP and the Gmail API, 60 s for SES and SMS) the factor gains `recovery_step` 0.10, up to 1 |
| `persistent_throttle_count` (8) throttles in a row | The "kept throttling" stop (a breaker, below) |

Manual mode never slows itself down, but it honours every pause and stop. All values are in
`DELIVERY_RATES["controller"]`.

## Seeds, by channel

Each channel's `DeliveryRatePolicy` row is created by migration `core.0036_delivery_rate_control` from
`DELIVERY_RATES["channels"]` (`config/settings/base/integrations/delivery_rates/channels.py`, every value with its
source URL), and re-created from the settings if it is deleted. Rates are in the channel's unit.

| Channel | Smart | Manual | Provider limit (ceiling) | Fallback | Headroom / burst | Daily and hourly limits (rolling) | Sources |
|---------|-------|--------|--------------------------|----------|------------------|-----------------------------------|---------|
| `graph_send` | on | 24 | 30 (documented) | – | 0.8 / 3 | 10,000 recipients a day; 500 external and 1,000 internal recipients an hour; until **Tenant limits confirmed**, campaigns also stay under 1,000 a day | Exchange Online limits ("30 messages per minute", 10,000 recipients a day); outbound spam policy, Standard preset |
| `graph_read` | on | 60 | 1,000 (documented) | – | 0.5 / 3 | – | Graph throttling limits: 10,000 requests per 10 minutes per app and mailbox, shared with sends |
| `ses_send` | on | 10, or the active config's campaign send rate | none documented; AWS reports `MaxSendRate`. Migration 0036 enters the active config's campaign send rate here (when above 0) | 1 (sandbox: "one message per second") | 0.9 / 2 | AWS reports `Max24HourSend` (−1 = none) and `SentLast24Hours` | SES sending quotas and `GetAccount` |
| `smtp_send` | on | 30, or the campaign send rate × 60 while SMTP is the active provider | none | 60 (app default, "limit unknown") | 0.9 / 1 | `smtp.gmail.com`: 2,000 messages a day; `smtp-relay.gmail.com`: 10,000 messages and 10,000 recipients a day | Workspace "send email from a printer, scanner or app" and SMTP relay pages |
| `gmail_imap` | on | 10 | none (Google publishes no IMAP rate) | 30 (app default) | 1.0 / 3 | – | Gmail IMAP "up to 15 email clients at a time"; bandwidth limits |
| `gmail_api_send` | on | 20 | 60 (6,000 quota units per minute per user ÷ 100 per `messages.send`) | – | 0.5 / 3 | 2,000 messages, 3,000 recipients, 2,000 external recipients a day; budget headroom 0.9; reserve 0.25 | Gmail API quota; Workspace sending limits; Gmail API error handling |
| `sms_send` | on | 1 | 1 (`SendTextMessage` quota per account and Region) | – | 1.0 / 1 | message parts/sec reported by `DescribePhoneNumbers` (fallback 1) | End User Messaging quotas; MPS per number type |

What Smart rate starts at with these seeds: Graph 24 messages/min (campaigns 19.2), Graph reads 500 requests/min,
SES 90 % of its bound (9 recipients/sec when migration 0036 carried over the default campaign send rate of 10), SMTP
27 messages/min climbing to 54 (no known limit, so it starts at half), Gmail IMAP 15 sessions/min climbing to 30,
the Gmail API 30 messages/min (campaigns 24), SMS 1 message/sec and no more message parts per second than the
number allows.

Migration 0036 carries over what the operator had set: the active email config's `max_send_rate` becomes the SES
manual rate and provider limit, and, while SMTP is active, the SMTP manual rate (× 60); the active Graph config's
messages per minute becomes the Graph manual rate (at most 30). A value above the documented limit is capped, and a
value too large for the column keeps the default.

**The carried-over SES provider limit gives way to AWS's.** It is stored as the Advanced **Provider rate limit** and
flagged as carried over (`provider_limit_carried_over`), so Smart rate has a bound before AWS can be read: the card
labels it "the old campaign send rate, until AWS reports the account's limit". As soon as `ses:GetAccount` reports a
limit for the account, that limit replaces it (higher or lower), and the card warns that the carried-over value no
longer applies. Entering another value, or clearing the field, makes it an ordinary operator limit; an operator limit
always applies, also below what AWS reports.

**SMTP campaigns are slower with Smart rate on.** SMTP servers report no limit and none is documented in general, so
Smart rate bounds SMTP by its 60 messages/min fallback and starts at 27 (campaigns 21.6), climbing to 54 (campaigns
43.2). The old campaign send rate (default 10 emails/sec, 600 a minute) is carried over only as the SMTP **manual**
rate, which Smart rate never reads. An installation that sends through SMTP and needs its old speed either enters the
server's real limit as the SMTP **Provider rate limit** under Advanced (Smart rate then uses it), or turns Smart rate
off so the carried-over manual rate applies. Production sends through SES or Microsoft Graph [CONFIRM LIVE].

**[CONFIRM LIVE]** Seeds that rest on assumptions about the real accounts:

- Whether the SES account and the SMS number are still in the sandbox (1 per second, a USD 1.00 spend limit).
- UC Merced's outbound spam policy for the Graph mailbox (`RecipientLimitExternalPerHour`,
  `RecipientLimitInternalPerHour`, `RecipientLimitPerDay`, `ActionWhenThresholdReached`) and the tenant's TERRL.
  Tick **Tenant limits confirmed** only once they are known.
- Whether staff also send from the Graph or Gmail sending account by hand. That sharing is why their headroom is
  below 1.
- Which Gmail API per-minute quota the Google Cloud project gets: a project that used the API before Google's 2026
  quota change may keep a larger one (raise the ceiling with `DELIVERY_RATES_OVERRIDES`).

### The manual rate now means the channel total

Before this change, the email config's **Campaign Send Rate** (`max_send_rate`, emails per second) paced queued mail
and campaigns only; sign-in codes and other mail sent from a request were not paced. The manual rate is now the
**total for the channel**: login codes, tickets, invitations, replies and test mail count against it, and campaigns
get at most `lanes.bulk_share` (80 %) of it. With the carried-over value, an SES campaign therefore runs 20 % slower
in manual mode than before, and at 72 % of its old speed with Smart rate on (0.9 headroom × 0.8 of the carried-over
limit) until AWS reports the account's limit, which then replaces the carried-over one. The campaign confirmation page
shows the resulting campaign rate and expected duration. To get the old speed back before AWS can be read, raise the
provider limit and the manual rate together, never above what the account allows. SMTP campaigns slow down more (see
above).

## Budgets, the transactional reserve and lanes

- **Daily and hourly limits** are rolling windows counted in `DeliveryUsageBucket` rows (`usage.bucket_seconds`, 5
  minutes, kept 48 hours). A limit is the smallest of the operator's value, the provider-reported one, the
  documented value and, for SMTP, the host profile.
- **Budget headroom** (`budget_headroom`, 1.0 except the Gmail API's 0.9): the share of each limit any mail may
  use.
- **Transactional reserve** (`lanes.transactional_reserve`, 10 %, or the channel's own value): campaigns stop at
  (1 − reserve) of what may be used, so sign-in codes, tickets and invitations keep the rest. For the Gmail API, mail
  stops at 1,800 messages a day and campaigns at 1,350.
- **Lanes.** Campaign mail is the **bulk** lane: at most `bulk_share` (80 %) of the rate, with its own schedule.
  Everything else is **transactional** and may use the whole rate. Only campaign mail is bulk: the email and SMS
  campaign jobs, the in-process campaign runners, and the resume of paused recipients.
- Over a budget, a request waits (or is deferred) until enough usage ages out. SES also counts what AWS reports it
  sent in the last 24 hours. A request larger than a whole daily limit is refused. An opt-out or other per-message
  refusal releases its usage.
- The status line shows each budget: "Last 24 h: 1,240 / 10,000 recipients (campaigns stop at 9,000)".

## Waiting, deferral and the background worker

How long a sender waits for its slot depends on where it runs (`DELIVERY_RATES["waits"]`): a request (login codes,
invitations, replies, test mail, a member's own ticket resend) 10 s, an inbox read 5 s, a background job 30 s, an
in-process campaign thread 900 s. Longer than that, the message is **not sent** and the caller is told when to try
again:

- **Sign-in codes.** "…try again in about N seconds" (HTTP 503 with `Retry-After`). An SMS code takes its slot before
  it locks the number, so a held-back code spends neither the number's hourly cap nor the daily SMS budget.
- **Background jobs** (`BACKGROUND_JOBS_ENABLED`) go back to the queue at their slot without using an attempt
  (`DeferredJobError`). The worker claims by priority (transactional mail 10, other jobs 50, campaign recipients
  100) and leaves a delivery lane's jobs unclaimed while that lane is paced, cooling down or stopped, so other jobs
  keep running.
- **In-process campaigns** (no worker) wait for each slot. On a longer hold the remaining recipients become **Paused
  by delivery limits** and the campaign ends **Partially sent**. **Resume paused recipients** on the Email Campaigns
  or SMS Campaigns list sends exactly those later (through the queue when jobs are enabled). A recipient the
  provider throttles, or otherwise holds back for now (a pause, a used-up quota), is sent again after the cooldown,
  email and SMS alike, at most `persistent_throttle_count` times; after that it and the rest are paused, never failed
  for it. An unconfirmed outcome is never sent again (it may have been delivered).
- **Bulk actions in one request** (Send All Tickets, the multi-select ticket resend, the invitation bulk resend) are
  refused above what one request can send in `waits.inline_request_budget_seconds` (25 s) at the current rate.
- **Inbox reads.** While Gmail IMAP or Graph reads are held back, the inbox list shows the last list read with a
  banner, and Import from Gmail says when to try again. Cached reads never take a slot.

A deferral always means "certainly not sent": the slot is taken before the provider is called, and a slot that never
reached the provider is given back.

## Stops (breakers) and Resume sending

When a provider says the account cannot send at all, the identity is **stopped**: for every lane, or for campaigns
only (SES `ConfigurationSetSendingPausedException`). Nothing is sent to the provider while it is stopped.

| The status line says | Typical cause | Ends |
|----------------------|---------------|------|
| "refused the credentials", "refused permission for this sender" | Graph `401` after a fresh token or `403`/`404` on a send, SMTP `534`/`535`, Gmail API token or permission refusals, SMS `NO_ORIGINATION_IDENTITIES_FOUND` | Saving the matching configuration lets the next request try at once; otherwise the timed probe |
| "reports sending is paused for this account" (campaigns only: "…for the configuration set") | SES `AccountSendingPausedException` or `GetAccount` `SendingEnabled: false`; `ConfigurationSetSendingPausedException` | The probe, a limit read showing sending enabled again, or Resume |
| "reports the 24-hour sending quota is used up", "reports the daily sending limit is reached", "reports the mailbox's submission quota is used up" | SES "Daily message quota exceeded" (probe after 10 minutes), SMTP `550 5.4.5` or the daily relay limit, Graph `ErrorSubmissionQuotaExceeded` | The probe |
| "reports the account's daily sending limit is reached", "suspended the account for exceeding its bandwidth limits", "reports the Google Cloud project's daily quota is used up" | Gmail API "(Mail sending)" `429`, bandwidth `429`, `dailyLimitExceeded`; Gmail IMAP `[OVERQUOTA]` | The probe (daily sending limit: the time Google names, else from 15 minutes up to 6 hours; bandwidth and project quota: after an hour) |
| "reports the monthly SMS spend limit is reached", "reports the account cannot send" | SMS `MONTHLY_SPEND_LIMIT_REACHED_FOR_TEXT`; `ACCOUNT_DISABLED`, `INSUFFICIENT_ACCOUNT_REPUTATION` | The probe (spend limit: hourly, at the latest at 00:00 UTC on the 1st of the next month), or a limit read showing a raised spend limit |
| "reports the sender mailbox is full" | Graph `507` | Saving the Graph configuration, or the probe |
| "kept throttling" | 8 throttles in a row | The probe |

Every stop has a **timed probe**: after `controller.breaker_probe_seconds` (900 s) exactly one request goes through.
Success closes the stop; another refusal doubles the interval, up to `breaker_probe_max_seconds` (6 hours).

On each card:

- **Resume sending** (shown while a pause or stop holds the channel) clears every cooldown and stop of the channel at
  once. It does not lift a daily limit. Use it after fixing the cause at the provider.
- **Reset Smart rate** starts Smart rate afresh at its start factor; cooldowns and stops stay.
- **Check provider limits now** (SES and SMS) reads the limits AWS reports for the identity in use.

Each save and button writes an admin history line, for example `sms_send: Smart rate on→off; manual 1→0.5`.

## Provider limit reads (discovery) and the IAM they need

Only AWS reports limits. Google and Microsoft report none at runtime, so their channels use the documented limits
and react to throttles.

| Channel | Reads | Shown on the card |
|---------|-------|-------------------|
| `ses_send` | sesv2 `GetAccount` (falls back to v1 `GetSendQuota`): maximum send rate, 24-hour quota, sent in the last 24 hours, whether sending is enabled, enforcement status, production access | All of them, with the read's age |
| `sms_send` | `DescribePhoneNumbers` or `DescribeSenderIds` for the number or sender ID in use (number type, message parts per second), and `DescribeSpendLimits` (monthly text spend limit) | All of them. The 1-per-second `SendTextMessage` quota is not reported |

- A read runs at most every `discovery_interval_seconds` (SES 1 hour, SMS 6 hours) per identity, with one attempt and
  a 5-second timeout. It is triggered by the worker's hourly maintenance, by **Check provider limits now**, and by a
  send that finds the read due. That send never waits for it: the read starts on a background thread after the
  send's admission, so Smart rate stays current without the worker. Opening the page does not call AWS.
- A failed read keeps the last-known values and shows the error, such as `AccessDenied: ses:GetAccount`.
- **Required infra change.** The reads use the shared application IAM credential (the secret behind
  `AWSCredentialConfig.credentials_secret_arn`), not the ECS task role. Grant that IAM user `ses:GetAccount`,
  `sms-voice:DescribePhoneNumbers` (already needed to find the number), `sms-voice:DescribeSenderIds` and
  `sms-voice:DescribeSpendLimits`. `ses:GetSendQuota` is an optional fallback. The policy lives outside this
  repository; `aws/cicd/identity-stack.json` grants the task role only Secrets Manager and Amplify actions, so it
  was not changed. **[CONFIRM LIVE]** whether that user already has any of these actions.
- Until `ses:GetAccount` is granted, Smart SES is bounded by the provider limit migration 0036 entered (the old
  campaign send rate), or by the 1-per-second sandbox fallback × 0.9 × 0.5 ≈ 0.45 recipients/sec when that rate was
  0. After the grant, clear that provider limit so the reported one applies ([above](#seeds-by-channel)). Smart SMS
  uses the 1-per-second quota and assumes 1 message part per second until the number is read.

## Provider answers

Each provider's answers are matched against `DELIVERY_RATES["signals"]` by an adapter in
`apps/core/services/delivery_rates/adapters/`. Free provider text is only matched, never stored or shown.

| Provider | Slow down | Pause | Stop | This message only |
|----------|-----------|-------|------|-------------------|
| Microsoft Graph | `429`, `503`, `509` (with `Retry-After`) | `ApplicationThrottled`, `ErrorExceededMessageLimit`; token endpoint busy | `ErrorSubmissionQuotaExceeded`; `401` after a fresh token, `403`/`404` on a send, `invalid_client`, `507` mailbox full | – |
| Amazon SES | `Throttling`, "Maximum sending rate exceeded" | – | "Daily message quota exceeded" (probe after 10 minutes; SES drops the message, so a retry is safe); `AccountSendingPausedException`; `ConfigurationSetSendingPausedException` (campaigns) | `MessageRejected` |
| SMTP | `421 4.7.0`, "Peak SMTP relay limit", SES SMTP rate | "Too many sign-in attempts" (5 minutes) | `550 5.4.5`, daily relay limit, daily quota; `534`/`535` | "receiving mail too quickly", `452 4.5.3` |
| Gmail IMAP | `[UNAVAILABLE]`, a login marked `[THROTTLED]` | "Too many simultaneous connections" (60 s) | `[OVERQUOTA]` / bandwidth (1 hour); `AUTHENTICATIONFAILED` | – |
| Gmail API | `rateLimitExceeded`, `408`, other `429`s | "Too many concurrent requests" (1 s); token endpoint busy | "(Mail sending)" `429`; bandwidth `429`; `dailyLimitExceeded`; token and permission refusals | `badRequest`, `invalidArgument` |
| AWS SMS | `ThrottlingException` | – | spend limit; `ACCOUNT_DISABLED`, `INSUFFICIENT_ACCOUNT_REPUTATION`; `NO_ORIGINATION_IDENTITIES_FOUND` | `ValidationException`, opted out |

Per-provider detail: [Microsoft Graph email](microsoft-graph-email.md#campaign-pacing),
[Gmail API email](gmail-api-email.md#errors-and-rate-signals), and
[Integrations](../architecture/integrations.md#aws-end-user-messaging-sms) for SMS and Gmail IMAP.

**[CONFIRM LIVE]** Provider behaviour the adapters assume but that was not observed:

- AWS: the exact SES v1 throttle code and texts; that the End User Messaging `Reason` is a top-level field; whether
  SMS traffic above the number's MPS is refused at once or queued, and whether `RateLimits` counts messages or
  parts; whether the spend-limit error is returned synchronously.
- Microsoft: the format of `Retry-After` on Outlook `429`s, and whether a quota breach is an error or a `202`
  followed by a non-delivery report.
- Google: the IMAP texts above (`[OVERQUOTA]`, "Too many simultaneous connections", `[THROTTLED]`); whether the
  sending account can get an app password for IMAP at all; and, for the Gmail API, the format of the retry time in a
  "(Mail sending)" `429`.

## Settings

Everything above is in `DELIVERY_RATES` (`config/settings/base/integrations/delivery_rates/`): `channels` (the seeds),
`controller`, `waits`, `lanes`, `usage`, `discovery`, `jobs` (background-job retries, the stale-claim recovery, the
deferral jitter, the lane-gate cache and the in-process runner's refresh) and `signals`. A deployment changes any of
them with the `DELIVERY_RATES_OVERRIDES` JSON, for example after an AWS quota increase:

```
DELIVERY_RATES_OVERRIDES='{"channels": {"sms_send": {"provider_limit": 20}}}'
```

The result is validated when settings load: an unknown key, a share or count out of range, a manual rate above its
provider limit, an hourly or external limit above the daily one, a worker wait not below the stale-claim recovery,
or an inline or read wait, or an SES or SMS `request_timeout_seconds` (10 s, connect and read, instead of botocore's
60 s), not below the inline request budget raises `ImproperlyConfigured` and stops every process before it starts.
Microsoft Graph's `GRAPH_REQUEST_TIMEOUT_SECONDS` (30), the Gmail API's `request_timeout_seconds` (15 per request; a
sign-in code without a cached token needs two) and the 30 s Gmail IMAP timeout are failure bounds that may exceed the
budget: they only end a stuck call, which the ALB idle timeout bounds in any case. Graph also caps `Retry-After` at
`GRAPH_MAX_RETRY_AFTER_SECONDS`; the smaller of that and `controller.retry_after_max_seconds` applies. See
[Environments](../deployment/environments.md#delivery-rates).

## Release notes

- **Kept for one release.** `EmailServiceConfig.max_send_rate` and `MicrosoftGraphProviderConfig.messages_per_minute`
  stay as hidden columns (migration `core.0037_retire_old_send_rates` makes both non-editable; only migration 0036
  reads them, for the carry-over) and the `DeliveryRateLimit` table stays. A follow-up release removes all three.
- **Deploy outside campaign sends.** During a rolling deploy the old tasks pace with `DeliveryRateLimit` and the new
  ones with this limiter, independently, so their combined traffic can reach twice the rate. An in-process campaign
  an old task is sending also keeps its old pacing until it ends.
- **Backward compatible with PR #643.** Production migrates before it replaces the service, so tasks of the running
  release (PR #643's Graph provider among them) still query the old columns while 0036–0038 apply; no migration here
  drops or renames a column they read.
- **Enable the background worker.** `BACKGROUND_JOBS_ENABLED` defaults to `false` (`deploy-backend.yml`). Without
  it, deferral, priorities and lane gating do not apply, campaigns run in a web process (and pause on long holds),
  and old usage buckets are never purged (at most 288 rows a day per identity in use). Set it to `true` in
  `itg/backend/deploy-config` before relying on Smart rate for campaigns. **[CONFIRM LIVE]** the production value.
- **Grant the IAM reads** listed above before or with the deploy, or Smart SES runs on the carried-over limit until
  they are granted (the reported limit replaces it on the first successful read).
- **Image rollback.** ECS rollback never reverses DDL. An image from before this change does not know the `gmail`
  provider: switch email to SES first. Its other columns are all still there (0037 only hides the old rate fields).

## Code map

| Concern | Where |
|---------|-------|
| Settings | `src/config/settings/base/integrations/delivery_rates/` (`channels.py`, `runtime.py`, `signals.py`, `validation.py`) |
| Models | `DeliveryRatePolicy` (`apps/core/models/base/delivery_rates.py`), `DeliveryRateState`, `DeliveryUsageBucket` (`apps/core/models/records/delivery_rate_state.py`), `BackgroundJob.priority` |
| Pure rules | `apps/core/services/delivery_rates/rules/` (`policy.py` precedence, `pacing.py` GCRA, `controller.py`, `signals.py`, `sms_parts.py`) |
| Runtime | `apps/core/services/delivery_rates/runtime/` (`limiter.py` admit, `feedback.py` record and release, `budget.py`, `breaker.py`, `discovery.py`), `families.py`, `maintenance.py`, `snapshot.py`, `status_text.py` |
| Provider adapters | `apps/core/services/delivery_rates/adapters/` (graph, ses, smtp, imap, gmail_api, sms); AWS reads in `apps/core/services/aws/quotas.py` |
| Call sites | `apps/core/services/email/delivery.py` (every email), `apps/core/services/aws/sms_send.py` (every SMS), `apps/mail/services/gmail_import/session.py` (every IMAP session), `apps/core/services/email/graph/mailbox.py` (Graph reads) |
| Worker | `apps/core/services/background_jobs/` (`worker.py` deferral and claim order, `gating.py`), `run_background_worker` ("Delivery-rate maintenance") |
| Admin | `apps/mail/admin/settings/rates.py`, `rates_forms.py`, `rate_cards.py`; templates `admin/mail/settings_rates.html`, `rate_card.html` |

Every channel's state, policy and usage rows are on the safe-ORM denylist, so the `i2g-admin` CLI cannot read or
change them.

## Not built (phase 2)

A parser for Graph non-delivery reports and learned limits; an SMS campaign spend guard from CloudWatch; IMAP
`[THROTTLED]` on commands other than login; listing the Gmail inbox by headers only, to spare the 2,500 MB a day IMAP
download limit.

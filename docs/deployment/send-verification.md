# Self-hosted email and SMS send verification

This site protects every user-triggered verification-code send with a
self-hosted ALTCHA proof of work **and** server-side destination, account, and
SMS-budget controls. Proof of work raises the cost of automated requests. It
does not independently prove that a request came from a human.

The open-source ALTCHA widget (`altcha` 3.2.2) and Python library (`altcha`
2.1.0) run entirely on project-controlled infrastructure. There is no ALTCHA
Cloud, Sentinel, or third-party CAPTCHA runtime.

## What is protected

| Entry point | Operation |
|-------------|-----------|
| `POST /authn/email-auth/request-code/` | `email_auth.request_code` |
| `POST /authn/phone-auth/request-code/` | `phone_auth.request_code` |
| `POST /authn/login/request-code/` | `login.request_code` |
| `POST /authn/register/` | `register` |
| `POST /authn/register/resend-code/` | `register.resend_code` |
| `POST /authn/password-reset/request-code/` | `password_reset.request_code` |
| `POST /authn/change-password/request-code/` | `change_password.request_code` |
| `POST /authn/delete-account/request-code/` | `delete_account.request_code` |
| `POST /authn/contact-emails/` | `contact_email.create` |
| `POST /authn/contact-emails/<id>/request-verification/` | `contact_email.request_verification` |
| `POST /authn/contact-phones/<id>/request-verification/` | `contact_phone.request_verification` |
| `POST /event/send-phone-code/` | `event.send_phone_code` |
| Django admin login: initial email, remembered account, resend | `admin.login.*` |

Ordinary ticket, notification, campaign, and transactional email is unchanged.
The Subscribe page has no endpoint of its own (`POST /authn/subscribe/` was
removed): it signs people in through the unified code flows above and then
edits the per-address `subscribe` flags as the signed-in member.

## Protocol

1. Client `POST /authn/send-verification/challenge/` with the operation and
   destination (never in a query string). Response is private (`Cache-Control:
   no-store`) and includes a signed ALTCHA challenge plus `challenge_id`.
   Admin forms instead use `POST /admin/send-verification/challenge/`, which
   accepts only admin operations and requires the form's CSRF token. This keeps
   the remembered-account cookie within its existing `/admin/` scope.
2. The browser solves the proof with a local worker (no CDN).
3. The send request includes `verification_challenge_id`, `verification_payload`,
   and a client-generated `send_request_id`. A new, explicit resend uses a new
   challenge and request id only after the previous attempt is resolved.
   Transport retries reuse the request id.
4. After authentication, one PostgreSQL transaction rechecks expiry/bindings,
   consumes the challenge once, reserves destination quotas, and inserts the
   send-request row. Delivery providers are called **after** commit. The SMS
   daily budget is reserved later, only when an SMS is actually handed to the
   provider (see [SMS daily budget](#sms-daily-budget)).
5. `GET /authn/send-verification/requests/<request_id>/` returns that client's
   recorded state. Other users' ids 404-equivalent (`verification_invalid`).

Public authentication operations always bind to the browser session, even when
an access token is present. Account operations and authenticated event SMS bind
to the member; admin sends bind to the admin browser session. Challenge, send,
and status lookup use the same policy. Expired credentials on protected
operations return 401 before proof consumption. Use the same-site API proxy and
send session cookies; this change does not enable unrelated cross-site cookies.
The web client's `withVerifiedSend` follows the same split: a change of the
stored login session cancels an in-flight send only for the member-bound
operations, and never for the public authentication operations.

The send context comes from validated business fields, not a client-selected
channel. Password reset accepts `identifier`, then the legacy `email` alias;
`destination` is a challenge convenience field and cannot override the send.
Password change and deletion reuse their validated recovery selection. Event
phone challenges use the sending endpoint's US-only normalization.

Idempotency compares the complete operation, channel, normalized recipient,
principal, and business fingerprint. The request is checked again after the
challenge lock; a unique-key conflict rolls back both consumption and quotas
before looking up the winning request. Only one `pending` to `sending` update
can claim dispatch. Neither time passing nor a lost response grants another
dispatch of a `sending` or `unknown` request.

Client error codes: `verification_required`, `verification_invalid`,
`verification_expired`, `verification_consumed`, `verification_context_mismatch`,
`verification_unavailable`, `send_unknown`, `send_throttled`,
`send_request_conflict`, `send_paused`. Throttled responses (`send_throttled`)
include `Retry-After`. (`verification_rate_limited`, the old per-IP challenge
limit, no longer exists.)

## Delivery outcomes and client recovery

Provider acceptance means that the provider accepted the request, not that the
message reached an inbox or handset. Explicit rejection/pre-dispatch failures
are definitely failed; a response lost after dispatch is unknown. Do not infer
this distinction from an HTTP status alone. Provider retries are disabled for
verification delivery; uncertain attempts retain both reservations and usable
OTP records until the OTP's normal expiry.

For ordinary sends, an uncertain first response or replay is HTTP 409 with
`code: send_unknown`, `request_id`, and `challenge_id` when applicable. The status
response includes `status`, `http_status`, `result`, and the same identifiers.
The frontend reconciles both that response and network errors before creating
any new request. It stores only unresolved request references/context hashes in
session storage, never a reusable proof. Reloads and repeated clicks query the
original request. Status-query failure remains unresolved, without automatic
resending; admin forms retain the equivalent reference in their session.

Password reset has a separate enumeration-safe public projection: eligible,
ineligible, accepted, failed, and uncertain delivery outcomes share a neutral
202 response and an opaque challenge ID. Its public status is `submitted`,
meaning the request was processed, not that delivery succeeded. Actual outcomes
remain internal, with reservations retained. This flow never automatically
resends either; a later explicit resend still requires a fresh proof and the
normal cooldown and budgets. A spent SMS daily budget is one more internal
outcome: the reset still answers the neutral 202 and the SMS is not sent (see
[SMS daily budget](#sms-daily-budget)).

## Abuse limits

- Destination-wide (email or phone, all entry points): 60-second cooldown and 10
  reserved/accepted sends per rolling hour for email. SMS keeps the existing
  durable 10/hour reservation on `PhoneVerificationChallenge.send_reserved_at`
  so the hourly SMS counter is not double-charged.
- Existing member/purpose email caps remain. Per-authenticated-user DRF throttles
  remain on the account and event send endpoints.
- Channel-wide SMS daily reservation is required in `enforce` mode. Leave it
  unset until production traffic is measured; enforce then fails closed for SMS,
  and the per-IP SMS fallback throttle stays on (see below). It counts SMS
  handed to the provider, nothing else: see
  [SMS daily budget](#sms-daily-budget).
- **No limit is keyed on the client IP** for challenge issuance, status lookup,
  email-code requests or any verification: campus users share one public IP, so a
  per-IP bucket throttles everyone at once while a rotating `X-Forwarded-For`
  barely slows an attacker. The removed limiters were the DRF challenge/status
  throttles (30 and 60 per minute) and the cache-based per-IP limiter inside
  challenge issuance (`enforce_challenge_rate_limit`, with its
  `SEND_VERIFICATION_CHALLENGE_CACHE_*` settings, which were never
  database-backed and are gone). The controls that remain are the ones above plus
  the ALTCHA proof bound to operation, destination and browser session (required
  in `enforce` mode only: in `observe` mode a request without a proof is accepted
  and just the destination quotas apply, so confirm which mode production runs),
  and the per-challenge attempt caps (email 5, SMS `MAX_VERIFY_ATTEMPTS` = 5,
  both cut to 1 for a destination under guessing attack; see
  [Code-guess degradation](#code-guess-degradation)).
- A new anonymous session does not grant a fresh global sending budget.

Every counter these controls depend on lives in **PostgreSQL**: single-use
proofs, destination quotas, the SMS daily reservation, request state, challenge
attempt counts and the password-login lockout (`authn_loginfailurewindow`, see
[Auth & Mail](../api/auth-and-mail.md#login)). They are shared by every ECS task
and Uvicorn worker and do not need Redis. Production has no Redis today and uses
a per-container file cache; see
[Environments: production cache](environments.md#production-cache-today) for
what still depends on that cache.

### SMS daily budget

`sms_daily_limit` (Site Settings, **Send Verification**) is one global counter
per UTC day: the `SendQuotaWindow` row `kind=sms_daily`, `scope_key=sms:global`.
It is the only global cap on SMS spend, and it is never keyed on the client IP.

**What spends it.** One unit per SMS handed to the provider, reserved in
`start_phone_verification` (`reserve_sms_dispatch`), the only place a
verification SMS leaves the system. A request that sends nothing spends
nothing: a password reset for a number that has no account, a number over its
own 10/hour cap, a request refused by the cooldown or the proof check, a
broken SMS template. So the budget cannot be used up without the same number
of SMS being handed to the provider (each one bounded by its number's cooldown
and hourly cap, and by the ALTCHA proof in `enforce` mode).

**Ordering and concurrency (PostgreSQL).**

1. The unit is reserved in the transaction that stores the code (the
   `PhoneVerificationChallenge` row, which is also the number's hourly
   reservation), as that transaction's last statement: the budget row is
   locked with `SELECT ... FOR UPDATE`, re-read under the lock, checked against
   the limit and incremented. Concurrent sends queue on that one row for the
   length of an `UPDATE` and a commit, so the last unit cannot be spent twice.
   It is the only lock taken after the challenge rows and no transaction takes
   another lock while holding it, so it cannot be part of a deadlock.
2. The transaction commits **before** the provider is called. A crash, a
   timeout or a provider error can therefore leave a unit reserved for an SMS
   that was not delivered, never an SMS sent without a unit.
3. The unit is **never released**: a failed or uncertain provider call keeps
   it, like the per-number hourly reservation. The count can overstate spend,
   never understate it.
4. When the budget is spent, the reservation raises and the whole transaction
   rolls back: no code is stored, the number's hourly cap is not charged, and a
   code the user already holds stays valid.

**What the caller sees when the budget is spent.**

| Flow | Answer |
|------|--------|
| Passwordless phone auth, password change by SMS, contact-phone verification, event phone code (an SMS is always sent) | `429 send_throttled`, "The SMS sending budget for today has been reached.", `retry_after: 3600` and `Retry-After: 3600`. A request that arrives after the budget is spent is refused before its proof and cooldown are used; one that loses the race for the last unit gets the same answer from the dispatch step. |
| Password reset with a phone identifier | The usual neutral `202`. No SMS is sent. |

**The password-reset rule.** The SMS budget never changes the answer of
`POST /authn/password-reset/request-code/`. A reset sends an SMS only when the
number belongs to an active account, so a budget refusal would be an answer
only real accounts can get, and would turn the endpoint into an
account-existence check once a day's budget is spent. Status, body and headers
are therefore the same for a number with and without an account in every budget
state: available, spent, and not configured. The refusals a reset can still answer are the ones
decided before the account is looked at and identical for every number: the
proof check, the per-destination cooldown (`429 send_throttled`, "Please wait
before requesting another code."), `503` while SMS is not calibrated in
`enforce` mode, and the per-IP fallback throttle while no budget is set. A user
whose reset SMS was dropped this way sees the neutral message and no SMS; the
operator sees the `quota_sms_daily` log line and its alarm
([Monitoring](#monitoring)), and reset by email keeps working.

### Code-guess degradation

A code is six digits. Each destination can be sent at most 10 codes an hour
(email: the destination-wide send quota above plus `MAX_CHALLENGES_PER_HOUR` per
purpose; SMS: `MAX_SENDS_PER_HOUR`), and each code normally allows 5 guesses, so
an attacker hammering one address or number used to get about 50 guesses an
hour (roughly a 0.12% chance a day of hitting a code).

`apps/authn/services/email/challenges/degradation.py` narrows that without any
client-IP key and without locking anyone out:

| Constant | Value | Meaning |
|----------|-------|---------|
| `FAILURE_THRESHOLD` | 10 | Failed guesses against one destination that trigger degradation |
| `FAILURE_WINDOW` | 24 hours | How far back failed guesses are counted |
| `DEGRADED_MAX_ATTEMPTS` | 1 | Guesses allowed by each code issued while degraded |

Failures are the existing `attempts` counters on `EmailAuthChallenge` rows (by
`target_email`, every purpose) and `PhoneVerificationChallenge` rows (by E.164
number, every purpose), counted over challenges issued in the window. Only codes
issued **after** the threshold is reached get one guess; codes already issued keep
their limit. Nothing else changes: requests answer as before, and the wrong guess
that spends a degraded code is answered exactly like a first wrong guess on any
other destination, the uniform invalid answer (HTTP 400), for email and for SMS,
on every verify endpoint. The code is spent all the same: the right code no
longer verifies and a new one has to be requested. (On a normal SMS code the
fifth wrong guess still answers `429` on the endpoints that tell the two apart;
a degraded code never gets a fifth guess, and guesses after the first keep
answering invalid.) The cap drops to about one guess per code sent (about 10 an
hour, roughly 0.024% a day).

The lever it creates is mild: anyone who can get codes sent to a victim's address
or number (ALTCHA, cooldown and hourly caps still apply) can make 10 wrong guesses
and leave that destination on single-guess codes for up to 24 hours. The owner
still receives codes and a correct first try still works; a typo costs one new
code request (60-second cooldown).

## Client-IP policy and residual risks

Sign-in, emailed-link, verification-code and ALTCHA flows deliberately have no
per-IP limit (the campus network is one IP). Also intentional:

- **The per-IP SMS throttle is only a fallback.** `sms_request_throttles()`
  (`apps/authn/security/throttles.py`) attaches `PhoneAuthCodeRequestThrottle`
  (5/minute) to `POST /authn/phone-auth/request-code/` and to `POST
  /authn/password-reset/request-code/` with a phone identifier **only while no
  SMS daily budget is configured** (`sms_daily_limit` unset or 0), or when the
  policy cannot be read. Once `sms_daily_limit` is set, every public SMS send
  reserves against it (in `observe` and `enforce` mode; `pause` sends nothing)
  and each number keeps its 60-second cooldown and 10/hour cap, so the throttle
  drops off by itself with no deploy. While it applies it is keyed on the raw
  `X-Forwarded-For` string like every DRF per-IP throttle
  (`REST_FRAMEWORK["NUM_PROXIES"]` is unset), so a forged header defeats it: a
  speed bump, not a budget.
- **The SMS daily budget is one global counter.** It is spent only by SMS
  actually handed to the provider (see [SMS daily budget](#sms-daily-budget)),
  so requests that send nothing, such as password resets for numbers without an
  account, cannot drain it. Someone who makes the site send real SMS to
  rotating numbers (passwordless phone auth sends to any number) can still use
  it up and stop SMS for everyone until the UTC day ends (email codes still
  work). That is the intended trade-off for bounding spend without an IP key:
  size the limit well above the campus peak day and alert on
  `send_verification.quota_sms_daily` (see [Monitoring](#monitoring)).
- **There is no global email or SMS hourly budget yet.** Email sends are capped
  per destination (60 s cooldown, 10/hour) but not in total, so rotating
  destinations can still spend SES budget; SMS has only the daily reservation. A
  global cap needs production volume numbers to size, and a constant-key cap is a
  lever for one attacker to lock everyone out, so none was added.
- Challenge issuance is unthrottled and writes one `SendVerificationChallenge`
  row per call (plus a session row for a client without one). The background
  worker's hourly maintenance removes them after the retention window and clears
  expired sessions, in batches of 1000 primary keys (see
  [Scheduled cleanup](#scheduled-cleanup)). Growth between runs is still bounded
  only by request volume: watch table size if it is abused.
- **Other tables that grow without an IP bound.** `authn_loginfailurewindow`
  gets two rows (the 15-minute and the 24-hour window) for every failed sign-in
  with an identifier not seen in those windows, unknown identifiers included;
  they stay until the window ends and the next hourly purge. `EmailAuthChallenge`,
  `PhoneVerificationChallenge`, `SendDestinationState` and `SendQuotaWindow`
  have **no retention at all**: nothing deletes their rows (see
  [Scheduled cleanup](#scheduled-cleanup)). Two anonymous endpoints outside the
  auth flows write rows as well:
  - `analytics_pageview` gets one row per accepted `POST /analytics/pageview/`
    and has **no retention**. A row is bounded in size (path and referrer 2,048
    characters each, user agent cut to 512), and the application records at most
    3,000 page views a minute per Uvicorn worker
    ([CMS and news API](../api/cms-and-news.md#post-analyticspageview)); below
    that cap the row count follows the request count.
  - The assistant audit log (`system_intelligence_assistantconversationlog` and
    `system_intelligence_assistantmessagelog`) gets a message row for every
    public chat or AI-search turn while audit logging is on, turns refused for
    budget included (requests stopped by the request-rate throttle are not
    logged). Rows older than the configured retention (default 90 days; 0 keeps
    everything) are deleted only when `python manage.py
    system_intelligence_cleanup` is run. It deletes in batches and does nothing
    when no configuration is active. The worker's scheduled maintenance
    deliberately does not run it, because deleting audit records is an operator
    decision: schedule the command if the retention setting should take effect.

  With no per-IP limit, request volume is the only bound on all of these (for
  the two anonymous endpoints, plus the off-campus edge rule in
  [WAF rate limits](waf-rate-limits.md), pattern set C); create the RDS
  free-storage alarm under [Monitoring](#monitoring).
- Password guessing is bounded per identifier by the failure lockout (10 failures
  in 15 minutes, 30 per day; `429 login_locked`), which can itself be used to
  lock one known account's *password* sign-in until the window ends (email-code
  sign-in still works).
- **Password spraying** (one password against many identifiers) stays under
  every per-identifier limit. It is detected, never blocked: 200 counted
  failures site-wide in one 5-minute window log one
  `login_guard.failure_spike` WARNING (see [Monitoring](#monitoring)). A global
  block would lock the whole campus out at once.
- CPU cost, mail bombing and spraying from **off-campus** addresses belong at the
  edge: see [WAF rate limits](waf-rate-limits.md), which never limits campus
  addresses per IP.

## Configuration

| Setting / Site Settings field | Local | Test | Production default |
|-------------------------------|-------|------|--------------------|
| `SEND_VERIFICATION_MODE` | `enforce` | `enforce` | `observe` until cutover |
| HMAC secrets | insecure local constants | test constants | required signing key initialized at startup; managed in **Send Verification** in Django admin |
| Cost | 500 | 10 | 5000 (env `SEND_VERIFICATION_COST`) |
| SMS daily limit | 1000 | 1000 | unset until calibrated |

Pause protected sends with mode `pause` (env or admin). Missing HMAC signing keys
prevent challenge issuance in **every mode**, including `observe`. Required
configuration and database failures also fail closed.

After migrations, the web entrypoint runs `initialize_send_verification` and
`verify_service_configs --strict --send-verification-only --require-sms` before
starting the server. Initialization creates an active `observe` configuration
with a cryptographically random signing key only when no configuration exists,
or fills an empty signing key on the existing active configuration. Repeated
starts retain the key, previous keys, mode, and all policy values. A PostgreSQL
transaction advisory lock serializes simultaneous initializations across
replicas. The background worker waits for the web container to become healthy.

Explicit `SEND_VERIFICATION_HMAC_SECRET` overrides skip database initialization;
the readiness check still validates their effective value, including an empty
override. Existing inactive configurations remain inactive. An intentional
`pause` produces a warning and permits server startup; missing/invalid effective
settings, or enforced SMS without its daily cap, block startup. This focused
check does not contact delivery providers or require unrelated service configs.

For an existing installation, run `python manage.py initialize_send_verification`
followed by the focused readiness command above. The command does not print
keys, rotate existing keys, change send policy, or send email/SMS. The broader
`seed_service_configs` command delegates its signing-key initialization to the
same command, but also seeds unrelated service and staff records.

For each policy field, an explicitly supplied setting/environment value wins,
then the active database configuration, then the documented default. Unset/None
means inherit. Local and CI settings are explicit overrides. An active admin
pause or an explicit environment pause always stops protected sends. The admin
shows the effective non-secret policy and each value's source; an environment
override must be removed before an admin edit to that field can take effect.

Invalid modes, algorithms, or numeric values return `verification_unavailable`
rather than falling back to observation or weaker limits. An explicit empty
HMAC value clears the setting; SMS daily limit 0 means uncalibrated and blocks
enforced SMS. Initial production defaults are cost 5000, challenge TTL 300s,
maximum proof size 8192 bytes, destination cooldown 60s, and email hourly cap 10.
Cost/hourly limits must be positive, TTL at least 30s, cooldown may be 0, and
the SMS cap must be positive before enforced SMS can run.

Rotate keys by copying current HMAC secrets into Previous, saving new current
values, and incrementing `key_version`. In-flight challenges verify against
current then previous signing keys and their stored issuance algorithm/cost,
so changing difficulty does not invalidate already-issued valid challenges.

Retention: pending challenges expire at five minutes; request rows are kept for
the 24-hour idempotency window plus `SEND_VERIFICATION_RETENTION_DAYS` (14),
then deleted by the scheduled cleanup below. Cleanup does not dispatch messages
or authorize a replay of a consumed/expired challenge.

### Scheduled cleanup

The `itg-background-worker` container (`run_background_worker`) runs these
maintenance tasks once at start and then every `--maintenance-seconds` (alias
`--key-purge-seconds`; default 3600, minimum 300), in this order:

| Task | Service | Removes |
|------|---------|---------|
| Retired RSA key purge | `purge_retired_auth_keypairs` | RSA keypairs retired more than 48 hours ago |
| Public assistant budget purge | `purge_expired_public_assistant_budgets` | Expired database budget rows (used when `REDIS_URL` is unset) |
| Send verification cleanup | `cleanup_expired_records` | Marks overdue pending challenges expired; deletes challenges and send requests past retention |
| Expired session cleanup | `clear_expired_sessions` | Expired `django_session` rows (`clearsessions` for the configured engine; the default database engine is used) |
| Login failure window purge | `purge_expired_failure_windows` | `authn_loginfailurewindow` rows whose window has ended (never lifts a live lock) |

Each task is isolated: a failure is logged as `<task name> failed` with a
traceback, and the remaining tasks and job processing continue. The
send-verification, session and login-window steps work through at most 1000
primary keys per statement, each batch committed on its own, so a large backlog
never holds one long transaction. Counts are logged only when something was
removed. `python manage.py cleanup_send_verification [--batch-size N]` runs the
send-verification step on demand. The tables are all database-backed, so
running maintenance in the worker container (which does not share the web
container's file cache) is correct.

A stop request (`SIGTERM`/`SIGINT`) is checked before every task and before
every batch of those three steps: the run ends after the batch in flight,
which has already committed, and the worker exits without waiting for the
backlog. Nothing is left half done; the next run (maintenance runs once at
worker start) carries on with the rows that remain. So even the large backlog
of a first run after a deploy cannot hold a shutdown past the worker
container's 120-second `stopTimeout`.

**Not cleaned up.** `EmailAuthChallenge` (`authn_emailauthchallenge`),
`PhoneVerificationChallenge` (`authn_phoneverificationchallenge`),
`SendDestinationState` (`authn_senddestinationstate`, one row per destination
ever requested) and `SendQuotaWindow` (`authn_sendquotawindow`, one SMS-budget
row per UTC day) have no retention: their rows are kept indefinitely. If a
retention step is added for the two challenge tables, it must keep **at least
24 hours** of rows: [code-guess degradation](#code-guess-degradation) counts
the failed guesses on challenges issued in the last 24 hours, and the SMS
hourly cap counts `send_reserved_at` over the last hour. Deleting younger rows
would reset both.

### Keyed payload fingerprint rollout

Business fingerprints use domain-separated HMAC-SHA256 with Django's
`SECRET_KEY`. Equivalent canonical payloads produce the same 64-character
fingerprint, and changing any business field still produces a request conflict.
These are idempotency checks; password storage continues to use Django's
password hashers.

Coordinate the backend cutover so instances do not alternate between the old
plain-SHA256 and new HMAC fingerprint formats. Transport retries for request IDs
stored before this change return `409 send_request_conflict`; they cannot
dispatch again or release reserved quotas. The same limitation applies when
rotating `SECRET_KEY`. Original payloads are not retained, so old fingerprints
cannot be converted in place. Do not delete request records or weaken the
fingerprint comparison to bypass this conflict.

An affected client should query the existing request's status endpoint under
the same session/member and resolve that outcome before a new explicit send.
Pending, sending, and unknown outcomes must not trigger an automatic new send.
The status endpoint remains accessible without recalculating the fingerprint.
The legacy conflict persists while the request row exists: by default, until
cleanup runs after the 24-hour idempotency window plus 14 retention days (about
15 days after creation, longer if cleanup is delayed). Expiry alone does not
authorize redispatch.

## Deployment plan

1. Apply migrations and deploy backend with `SEND_VERIFICATION_MODE=observe`.
   Startup initializes a missing signing key and checks the effective email/SMS
   send policy before serving traffic. If existing configurations are all
   inactive, explicitly activate the intended configuration in Django admin;
   startup never chooses one automatically. Do **not** send live email/SMS as
   part of this change.
2. Deploy frontend and admin assets that issue challenges and attach proofs.
   Keep compatible widget/worker files for rollback. Admin widget URLs must
   resolve through Django static storage (S3 in production), not a hardcoded
   backend `/static/` path. The vendored widget embeds its blob workers; retain
   the existing CSP without broader script or worker permissions.
3. Calibrate SMS daily limit from observed traffic and budget. Provider-side
   AWS End User Messaging limits remain the monetary backstop; message counts
   are not an exact dollar cap.
4. Remove the temporary `SEND_VERIFICATION_MODE=observe` override and select
   Enforce in the active admin configuration, or explicitly set the environment
   override to `enforce`. Confirm the admin's effective-policy display before
   cutover. Observation mode must have a defined end and must not remain as a
   client-selected bypass.

Rollback after enforcement: revert to a compatible protected frontend/backend
pair, or pause sending. Disabling server verification while leaving public
sends open is not the default rollback.

Stale clients that omit proofs receive `verification_required` and must reload
the current UI.

## Pending

- Production SMS daily limit and PoW cost calibration from live traffic.
- Authorized live smoke test of one email and one SMS path after enforce.
- Confirm in Django admin → Site Settings → **Send Verification** (the
  repository cannot see production values): the effective **mode** (`observe`
  accepts sends without a proof) and **SMS daily limit**. While the limit is
  unset the per-IP SMS fallback throttle stays on; setting it turns the throttle
  off with no deploy. Enforced SMS refuses to send until it is set.
- Decide on a global email/SMS hourly budget once production volume is known.
- Create the CloudWatch alarms under [Monitoring](#monitoring) and the edge rules
  in [WAF rate limits](waf-rate-limits.md).

## Regression gate

Run `apps.authn.tests`, `apps.core.tests.commands.test_seed_service_configs`,
`apps.core.tests.commands.test_initialize_send_verification`,
`apps.core.tests.commands.test_verify_service_configs`,
`apps.core.tests.commands.test_run_background_worker`,
`apps.event.tests.views.test_sms_views`, and
`apps.event.tests.views.test_phone_verification` with mocked delivery. Dedicated
verification tests disable automatic proof attachment. The API coverage matrix
checks all 12 sending routes before account/contact mutations.

Run `apps.authn.tests.services.test_send_verification_concurrency` and
`apps.authn.tests.services.test_login_guard_concurrency` against an isolated
PostgreSQL 16 database with `config.settings.test` and the `DB_*` variables (CI
does). SQLite skips are not evidence of locking correctness. Contention and
fault tests must check provider calls, reservations, challenge consumption,
rollback, and retained OTPs, not just the database vendor name.

Browser regression tests must use the installed widget and actual worker with
valid low-cost challenges, without an injected proof or mocked solver. Cover
React, all three admin branches, real cookie path behavior, configured static
origins, solver errors, cancellation, duplicate clicks, and uncertain results.
Run frontend lint/types/build and migration consistency checks before review.

## Monitoring

Structured logs use the `apps.authn.send_verification` logger with hashed
destinations. Events include `challenge_issued`, `challenge_consumed`,
`proof_invalid`, `quota_*`, `send_rejected`, `send_finalized`, `request_replay`,
and `cleanup`. Do not log OTPs, HMAC secrets, or full proof payloads.

Production logs are plain text lines (`LEVEL time module pid tid message`) in
the task's CloudWatch Logs group (`ECS_LOG_GROUP`, default `/ecs/itg-backend`;
demo `/ecs/itg-backend-demo`), `ecs/` streams for web and `worker/` for the
worker. Two log alarms and one storage alarm (below) are worth creating now:

| Signal | Filter pattern | Meaning |
|--------|----------------|---------|
| Password spraying | `"login_guard.failure_spike"` | WARNING from `apps.authn.services.login_guard`, at most once per 5-minute window, when site-wide password-login failures reach `SPRAY_ALERT_THRESHOLD` (200): `login_guard.failure_spike failures=200 window=5m threshold=200`. Detection only; nothing is refused. |
| SMS budget exhausted | `"send_verification.quota_sms_daily"` | An SMS was not sent because `sms_daily_limit` is spent; SMS stays off for everyone until the UTC day ends. |

```bash
aws logs put-metric-filter \
  --log-group-name /ecs/itg-backend \
  --filter-name login-guard-failure-spike \
  --filter-pattern '"login_guard.failure_spike"' \
  --metric-transformations metricName=LoginFailureSpike,metricNamespace=I2G/Auth,metricValue=1,defaultValue=0

aws cloudwatch put-metric-alarm \
  --alarm-name i2g-login-failure-spike \
  --namespace I2G/Auth --metric-name LoginFailureSpike \
  --statistic Sum --period 300 --evaluation-periods 1 \
  --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions <SNS topic ARN>
```

Repeat with the second pattern (for example `SmsDailyBudgetReached`). The
per-identifier line `Password sign-in locked: window=15m|24h
identifier_hash=<12 hex>` is also logged at WARNING when one identifier trips a
lockout window; it carries no email or phone and is useful for dashboards
rather than paging. Tune `SPRAY_ALERT_THRESHOLD` against the observed baseline
once the metric has some history.

Limits of the spray alarm: it counts one clock-aligned 5-minute window at a
time and fires on the failure that makes the count exactly 200. A burst that
straddles a window boundary (up to 199 failures at the end of one window and
199 at the start of the next) and a spray paced under 200 per 5 minutes (about
57,000 guesses a day) raise no alarm. It is a tripwire for fast sprays, not a
measure of failed sign-ins; the WAF `campus-auth-count` rule
([WAF rate limits](waf-rate-limits.md#6-alarms)) and the per-identifier lockout
lines cover part of the gap.

`send_verification.quota_sms_daily` is logged each time an SMS could not be
sent because the budget was spent, including password resets that still
answered their neutral `202`.

**Database storage.** Several auth tables grow with request volume alone (see
[Client-IP policy and residual risks](#client-ip-policy-and-residual-risks)).
Create an RDS `FreeStorageSpace` alarm on the production instance (namespace
`AWS/RDS`, dimension `DBInstanceIdentifier`; for example below 20% of allocated
storage for 15 minutes), so a flood of failed sign-ins or challenge requests is
noticed before the disk fills:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name i2g-rds-free-storage-low \
  --namespace AWS/RDS --metric-name FreeStorageSpace \
  --dimensions Name=DBInstanceIdentifier,Value=<instance id> \
  --statistic Minimum --period 300 --evaluation-periods 3 \
  --threshold <bytes: 20% of allocated storage> \
  --comparison-operator LessThanThreshold \
  --alarm-actions <SNS topic ARN>
```

## Repair validation recorded on 2026-09-05

The repair addresses the 14 reviewed defects: actual recipient/channel binding,
React widget readiness, effective admin policy, production admin asset URLs,
operation-aware identity, remembered-cookie scope, uncertain delivery outcomes,
complete idempotency context, post-lock replay lookup, transaction conflict
rollback, malformed proof cost, widget error states, contact-email domain errors,
and event US-phone normalization. Additional regressions cover stable public
password-reset IDs, registration password fingerprints, and oversized challenge
destinations.

- PostgreSQL 16: **1043 backend tests passed**, with no skips, covering authn,
  related event SMS/phone views, and service-configuration commands. This includes
  actual contention tests using separate connections and barriers that force
  both initial request lookups to miss.
- After integration with current main, **1645 Vitest tests passed** across 143
  files. Coverage is 95.85% statements, 87.50% branches, 96.23% functions, and
  96.76% lines, meeting the unchanged repository thresholds.
- Chromium: **30 browser tests passed**, including seven real-widget/recovery
  tests and 23 existing login, phone, reset, and subscription journeys. The
  admin static-origin test serves the vendored UMD asset without CORS headers;
  the browser tests do not inject solved verification payloads.
- Django's five admin-adapter regressions passed, including CSRF rejection,
  remembered-cookie context, operation isolation, and static-storage URLs.
- Python Ruff, scoped frontend ESLint, TypeScript/production build, migration
  consistency, and whitespace checks passed.

Current-main integration also exercised 1087 PostgreSQL backend tests including
the provider-neutral email suites. Two legacy rejection fixtures needed the
provider error type used by SES/SMTP; after aligning them, all 20 tests in the
affected email API module passed on rerun. Six new transport regressions verify
SES/SMTP single dispatch, OTP retention after ambiguous outcomes, and confirmed
SMTP acceptance followed by a failed QUIT. The independent email and send-policy
migration branches are joined by a new merge migration.

All delivery providers were mocked. These results do not constitute production
deployment, live SMS/email delivery validation, or production budget calibration.

# Request limits (Smart limit and manual limit)

Every request the site answers goes through one limiter, `apps.core.middleware.RequestRateLimitMiddleware`: DRF and
plain Django views, the Django admin, the `i2g-admin` CLI API (`/admin-api/`) and webhooks. It limits by **scope** (a
group of endpoints), and every scope has a **priority tier**, so under load the site sheds bulk and background work
before anything a person is waiting for, and never the verification code a person just asked for. The policies are
edited on **Site Settings → Request Limits** (`/admin/core/request-limits/`). The finer per-view limits (DRF
throttles, the sign-in lockout, code cooldowns, the SMS daily budget) still apply underneath; their rates are
request-limit policies too ([API: Throttling](../api/index.md#throttling)).

It mirrors the [delivery-rate limiter](delivery-rates.md) for outgoing messages: Smart limit is on by default for every
scope and takes priority over the manual limit, the controller is priority-ordered AIMD, and every change is in the
admin log.

## Priority tiers

| Tier | What | Under overload |
|------|------|----------------|
| **P0 critical** | User-initiated sign-in and verification: verification-code send and check, password sign-in, email-link exchange, ALTCHA challenge, token refresh, session check, event check-in scan, the SES webhook | Never tightened for load and may use every concurrency slot. Only its abuse limits apply |
| **P1 interactive** | What a person waits for on screen: public and member page data, form submits, registrations, admin pages, the CLI | Cut last, by ×0.85 a step (floor 0.5); restored first |
| **P2 background** | Automatic or repeating requests: admin status polling, page-view telemetry, CSP reports, sitemap, embed host refresh, code requests without a valid proof | ×0.7 a step (floor 0.25) |
| **P3 heavy** | Full-list catalog reads, AI search and assistant, admin exports / imports / syncs / campaign sends, unmatched-path (404) scanner traffic | Cut first, ×0.5 a step (floor 0.1); restored last |

A tier is a per-scope, admin-editable field. **Priority is not an exemption from abuse protection**: a P0 code request
keeps its destination cooldown, hourly cap, SMS daily budget, challenge attempt cap and sign-in lockout, and a caller
who collects repeated 429s is blocked with a growing cooldown ([Abuse escalation](#abuse-escalation)).

**User-initiated only.** An anonymous verification-code request is P0 only when its body carries a valid
send-verification (ALTCHA) proof, checked without spending it (`apps/authn/services/send_verification/priority.py`); a
signed-in person is P0 anyway. Anything else is counted in the shared P2 scope `auth-code-unproven` and shed like
background traffic. A promoted code goes out on the transactional lane of the delivery-rate limiter, so it is never
queued behind a campaign ([Delivery rates: lanes](delivery-rates.md#budgets-the-transactional-reserve-and-lanes)).

## Scopes and routes

A request's scope is decided in `process_view`, after URL resolution (`apps/core/services/request_limits/scopes.py`):

1. **Exempt**: a CORS preflight (`OPTIONS`), a view with `rate_limit_exempt = "reason"`, an app's
   `register_exemption(...)` or `REQUEST_RATE_LIMITS["exempt"]`. Exempt today: `/livez/`, `/readyz/`, `/health/`
   (answered by `HealthCheckMiddleware` before the limiter runs), `/layout/theme.css`, `/robots.txt`, one-click
   unsubscribe (RFC 8058, a legal opt-out), the current-projects redirect and the development-only static views.
2. The **route table** `REQUEST_RATE_LIMITS["routes"]` (Django-admin and third-party routes; it wins, so a deployment
   override can move any route).
3. The view's own **`rate_limit_scope`** (a scope, or `{"GET": "scope", "*": "scope"}`).
4. An app's **`register_scope(...)`** from `AppConfig.ready()`.
5. Otherwise a **fallback**: `cli` under `/admin-api/`, `staff-admin` under `/admin/`, else `public-read` /
   `member-read` for GET and HEAD and `public-write` / `member-write` for the rest. Paths no route matches are
   limited after their 404 in `not-found` (P3).

So no route is ever unlimited by accident. `apps.core.tests.request_limits.test_coverage` walks the whole URLconf and
fails when a site view names no scope or exemption, or when a table key matches no route. A new view sets
`rate_limit_scope` (or `rate_limit_exempt` with its reason).

Scope seeds, tiers and identities: `src/config/settings/base/integrations/request_limits/scopes.py` (route scopes)
and `view_scopes.py` (the 24 per-view limits, `view-…`, each with a `parent` route scope whose Smart factor it
follows).

## Who a request counts against

Each scope's `identity` picks the bucket key (`apps/core/services/request_limits/identity.py`):

| Identity | Key |
|----------|-----|
| `member` | The verified member (the JWT's signature, expiry, type, audience and issuer checked offline with SimpleJWT, no query; a forged claim is never read) or the signed-in admin user. Anonymous callers count only toward the scope's aggregate cap |
| `session` | The signed-in admin user |
| `cli` | The SHA-256 of the CLI token, else the member |
| `destination` | A key an app registers with `register_identity_resolver` (none today), else the member; anonymous callers count only toward the aggregate cap |
| `ip` | The signed-in person if any, else the CLI token, else the client IP (`apps.core.utils.client_ip`, `NUM_PROXIES`) |
| `global` | No per-caller bucket, only the aggregate cap |
| `view` | A per-view limit: the view keeps its own key (member, visitor token, challenge, …) |

**Sign-in and code flows are never keyed on the client IP** (most users share one campus address). The IP is used
only for anonymous callers of scopes where a single source flooding is the risk: public reads (3,000/min per IP, a
ceiling far above any honest browser, with 12,000/min site-wide), public writes, tokenized links, the legacy viewer,
public background requests, telemetry, full-list catalog reads, AI, 404s and the SES webhook. See
[Environments](../deployment/environments.md#what-still-keys-on-the-client-ip).

## Smart limit or manual limit

Each policy has a **Smart limit** switch (on by default; "Adjusts the limit automatically to actual conditions (load,
error rate, abuse)", the delivery-rate wording) and a **manual limit**, kept while Smart is on and used again when it
is turned off. The precedence (`rules/limits.py`):

```
baseline B = the scope's REQUEST_RATE_LIMITS "requests", capped by the per-caller ceiling
Smart on : factor f = 1 for P0 and fixed scopes, else clamp(Smart factor, Smart floor, 1)
           per caller = max(1, ⌊B × f⌋), everyone together = max(1, ⌊global cap × f⌋)   # manual not read
Smart off: per caller = min(manual, ceiling), everyone together = global cap
Per-process counters: each limit ÷ live processes, rounded up (never 0)
```

The **per-caller ceiling** and the **aggregate cap** are deployer maximums from `REQUEST_RATE_LIMITS`: staff can lower
them on the policy, never raise them; a deployment that lowers one applies to existing rows at once. A **fixed** scope
(token refresh, session check, check-in desk and status, the SES webhook) is never tightened by Smart.

### How Smart limit reacts

Each web process measures its own signals in 15-second windows (`controller` in `runtime.py`): p95 response time,
the 5xx share (both once a window has 20 requests), the mean share of its concurrency slots in use, and requests
refused for lack of a slot. The first request to finish after a window ends assesses it
(`apps/core/services/request_limits/runtime/smart.py`; no background worker):

- **Overload** (any of: slots ≥ 75 % in use, a slot refusal, 5xx ≥ 5 %, p95 ≥ 1,500 ms): every sheddable scope of
  the **lowest tier that still has room** and had traffic in the window is multiplied by that tier's decrease factor.
  P3 is cut to its floor before P2 is touched, then P1. P0 and fixed scopes are never cut.
- **Healthy** (slots < 40 %, 5xx < 1 %, p95 < 800 ms): the **highest** tier still below full is restored by its
  recovery step, P1 first, then P2, then P3, but not a scope cut in the last 30 seconds.
- Otherwise **steady**: nothing changes.

Factors are stored per scope in `RequestRateLimitState` (with the decision and its signal values), written
compare-and-set so two processes never overwrite each other, and every process re-reads them at most every 10
seconds. Turning Smart off for a scope resets its factor to 1, so turning it on again starts at full speed.

### Reserved slots (admission control)

A process accepts at most `UVICORN_LIMIT_CONCURRENCY` (default 20) requests at once. A request is admitted only while
the slots in use are below its tier's share: P1 90 %, P2 70 %, P3 50 %, and two slots are always left to P0. A lower
tier over its share gets a 429 with `Retry-After: 2` while P0 still gets through.

### Abuse escalation

Every 429 one caller collects in a scope is a strike, whoever refused it: this limiter or the view's own limit (a code
cooldown, an hourly cap, the SMS budget, the sign-in lockout). Ten strikes in five minutes block the caller for that
scope for 30 seconds, doubling with every block within an hour, up to 15 minutes. "Everyone together" is never
blocked.

## Counters

| Mode | When | How |
|------|------|-----|
| **Shared** | The default cache is Redis (`REDIS_URL` set) | One atomic counter per bucket and window for every process: each limit holds site-wide |
| **Per process** | No shared cache (production today) | Each process counts in its own in-process `throttle` cache and allows `limit ÷ live processes`. Each process keeps a `RequestLimitProcess` heartbeat row, refreshed at most every 30 s on the request path (one UPDATE and one COUNT per interval, never per request); a row not refreshed for 90 s stops counting and is deleted after a day. A database error keeps the last count |

`store.mode` (`auto`, `shared`, `local`) can force one. Windows are fixed (two cache calls a request, no lock); a
caller can send up to twice a limit across a window boundary, which is accepted for a flood guard. Every counter call
fails open: a cache error lets the request through and is logged. Keys are hashed, so no IP or token appears in a
cache key. Recent 429s are counted per scope and minute in the same store (kept 15 minutes).

## The 429 answer

`{"detail": "Too many requests. Please try again in N seconds.", "code": "rate_limited", "retry_after": N}` with
`Retry-After: N` and `Cache-Control: no-store`, exposed to the cross-origin SPA (`CORS_EXPOSE_HEADERS`). The SPA, the
admin pollers and the CLI wait it out ([API: Throttling](../api/index.md#throttling)).

## Settings

`REQUEST_RATE_LIMITS` (`src/config/settings/base/integrations/request_limits/`) has `scopes`, `routes`, `exempt`,
`tiers`, `controller`, `admission`, `abuse`, `store` and `fallback`; each value is commented where it is defined. A
deployment changes any of them with the `REQUEST_RATE_LIMITS_OVERRIDES` JSON, deep-merged strictly (an unknown key is
an error; `routes` and `exempt` may gain entries, and `null` removes one):

```
REQUEST_RATE_LIMITS_OVERRIDES='{"scopes": {"public-read": {"global_cap": 20000}}}'
```

The result is validated at import, so a bad override raises `ImproperlyConfigured` before the site serves a request.
What an override changes on a running site: a scope's `requests` (the Smart baseline), its ceilings (`identity_ceiling`,
`global_cap`), routes, exemptions and every runtime section apply at once. The other scope keys (tier, manual limit,
Smart switch, floor, fixed, enabled) only **seed** a policy row that does not exist yet; an existing row is changed
in the admin. `REQUEST_RATE_LIMITS_ENABLED` turns the whole limiter off. See
[Environments](../deployment/environments.md#request-limits).

## Runbook

### Reading Site Settings → Request Limits

Superusers and staff with access to the Core app (System) view and edit it; other staff get 403. The page refreshes
its status every 15 seconds.

- **Now** (summary): one line per tier (*protected*, *full baseline*, *Smart is shedding it* with how many scopes are
  below baseline and the lowest factor, or *recovering*); this process's last assessment (`overload: 92% of request
  slots in use → shed P3`); its request slots, the share each tier may fill and the P0-only ones in use; and the
  counter mode with the live process count. The assessment and slots are those of the process that answered the page.
- **Each scope card**: `Now: 3,000 / minute per caller · everyone together 12,000 / minute · Smart ×1.00`; with
  per-process counters the per-process share; why the factor is what it is (`Smart ×0.50 of the baseline: cut at
  14:02 because of p95 response time 1900 ms`, or *Fixed*, or *Smart limit is off*); and the 429s of the last
  15 minutes, split into *by this limiter* and *by the view's own limits*. Per-view limits sit under their tier in
  **Finer per-view limits**.
- Every saved change is an admin log entry (`auth-code-send: priority P0->P1; manual 10->20`), linked from the page.

### Legitimate users get 429

1. Find the scope with recent 429s. *By the view's own limits* means a finer limit (a code cooldown, the sign-in
   lockout, a per-member throttle) refused them: that is usually intended; check the per-view card.
2. *By this limiter* with a factor below 1 and an *overload* reason: Smart is shedding because the site is
   overloaded. It restores the tier by itself once the signals are healthy; fix the load (scale out, find the slow
   endpoint) rather than the limit.
3. A full factor (×1.00) and still refused: the baseline is too low for real traffic. Short term, turn **Smart limit**
   off on that card and set a higher **manual limit** (applies within 10 seconds on every process). It cannot exceed
   the per-caller ceiling; raising that, or the baseline Smart scales, takes a `REQUEST_RATE_LIMITS_OVERRIDES` deploy.
   Turn Smart back on afterwards.

### A flood or abuse

- Lower the scope's manual limit with Smart off, or lower its **aggregate cap** under *Advanced* (allowed: caps are
  lowered, never raised). Moving a scope to P3 makes Smart shed it first and limits its slots to half.
- A repeat offender is already blocked by abuse escalation (up to 15 minutes per scope). Per-IP floods from
  off campus belong at the edge ([WAF rate limits](../deployment/waf-rate-limits.md)).

### Switching a scope off

- **One scope**: clear **Enabled** under *Advanced* on its card. A route scope is then not limited at all (its finer
  per-view limits still apply); a per-view limit is removed.
- **One route, by deploy**: `REQUEST_RATE_LIMITS_OVERRIDES='{"exempt": {"<namespace:route-name>": "reason"}}'`.
- **Everything**: `REQUEST_RATE_LIMITS_ENABLED=false` in the backend environment and redeploy. The middleware then
  lets every request through and the per-view throttles use their seeds, as before this feature; the sign-in lockout,
  send-verification quotas and the SMS daily budget are unaffected.

The limiter never takes the site down with it: an error inside it is logged (`request_limits.admit_failed`,
`request_limits.finish_failed`, `request_limits.store_unavailable`, `request_limits.policy_unavailable`,
`request_limits.heartbeat_failed`) and the request goes through. Smart decisions are logged as
`request_limits.smart <action> <tier> {scope: factor}`.

## Code map

| Concern | Where |
|---------|-------|
| Settings | `src/config/settings/base/integrations/request_limits/` (`scopes.py`, `view_scopes.py`, `routes.py`, `runtime.py`, `validation.py`) |
| Models | `RequestRateLimitPolicy` (`apps/core/models/base/request_limits.py`), `RequestRateLimitState`, `RequestLimitProcess` (`apps/core/models/records/request_limit_state.py`); migrations `core.0039`, `core.0040` |
| Middleware | `apps/core/middleware/request_limits.py` (after CORS, health checks and authentication; the `core` system checks refuse another order) |
| Pure rules | `apps/core/services/request_limits/rules/` (`limits.py` precedence and slot shares, `controller.py`) |
| Runtime | `apps/core/services/request_limits/` (`limiter.py`, `scopes.py`, `identity.py`, `priority.py`, `view_limits.py`), `runtime/` (`store.py`, `heartbeat.py`, `registry.py`, `signals.py`, `smart.py`, `abuse.py`, `refusals.py`) |
| App hooks | `register_scope`, `register_exemption`, `register_identity_resolver`, `register_priority_check` from `AppConfig.ready()` (authn registers the code-send proof check) |
| Admin | `apps/core/admin/request_limits/` (`views.py`, `forms.py`, `cards.py`); templates `admin/core/request_limits.html`, `request_limit_card.html`; `admin/js/poll-backoff.js` |
| Clients | `pages/src/lib/api/rateLimit.ts` (SPA), `cli/src/i2g_admin/client/rate_limit.py` (CLI) |

The policy, state and heartbeat rows are on the safe-ORM denylist, so the `i2g-admin` CLI cannot read or change them.

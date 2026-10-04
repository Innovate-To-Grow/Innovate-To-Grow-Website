# WAF rate limits (campus-aware)

Runbook for AWS WAF rate-based rules in front of the unauthenticated auth
endpoints and the two anonymous write endpoints (page-view tracking and the
public assistant chat). It covers what the application deliberately does not
do: per-IP limits against password spraying, CPU exhaustion, mail/SMS bombing
and request floods from outside the campus.

**Constraint.** UC Merced users mostly reach the site from a few shared campus
egress addresses. A per-IP limit on those addresses throttles the whole campus
at once. So:

- The application has **no** per-IP limit on the sign-in, emailed-link,
  verification-code and ALTCHA endpoints. Among the endpoints in this runbook
  (section 3) one per-IP throttle remains: the SMS fallback on
  `/authn/phone-auth/request-code/` and on `/authn/password-reset/request-code/`
  with a phone identifier (5/minute, active only while no SMS daily budget is
  set). See
  [Send verification](send-verification.md#client-ip-policy-and-residual-risks).
  The few per-IP keys elsewhere in the application (none of them limits a
  campus user) are listed in
  [Environments](environments.md#what-still-keys-on-the-client-ip).
- At the edge, per-IP rules apply **only to addresses outside the campus IP
  set**. Campus traffic is counted and alarmed, **never blocked per IP**.
- Every rule starts in **COUNT** and moves to **BLOCK** only after calibration.

These rules sit on top of the in-app controls (per-identifier lockout,
per-destination quotas, ALTCHA, code-guess degradation, spray alarm); they do not
replace them.

## 1. Campus IP set

Get the ranges from **UC Merced campus IT**. Do not guess them, look them up in
a registry, or infer them from traffic (the busiest addresses in the logs may be
an attacker). Ask for every egress the campus uses, IPv4 and IPv6: campus NAT,
VPN, wireless (including eduroam) and residence-hall networks if they egress
separately.

- Create one IP set per address family (for example `ucm-campus-egress-v4` and
  `ucm-campus-egress-v6`) in the **same scope and region as the web ACL**:
  `REGIONAL` in `us-west-2` for the ALB, `CLOUDFRONT` (managed in `us-east-1`)
  for CloudFront or Amplify.
- Put the source (ticket or contact, date) in the IP set description and
  re-confirm it with campus IT every term. A stale set means campus users fall
  under the off-campus per-IP rules.
- Until campus IT has confirmed the set, keep every rule in COUNT.

## 2. Which client IP WAF sees

A rate-based rule keyed on IP uses the address of the connection that reaches
the resource the web ACL is attached to. That depends on the path a request
takes, and the repository shows two.

Known from the repository:

- **Direct to the API origin.** The production frontend's default API base is
  `https://api.i2g.ucmerced.edu` (`deploy-frontend.yml`), so browsers call the
  API origin directly. `NUM_PROXIES = 1` in the production settings and
  [Request flow](../architecture/request-flow.md) assume the ALB is the only
  proxy on that path.
- **Through Amplify.** The demo frontend's default API base is
  `https://demo.i2g.ucmerced.edu/api`: Amplify Hosting (CloudFront) rewrites
  `/api/<*>` to the backend origin (`amplify_redirects.py`, target
  `AMPLIFY_BACKEND_PROXY_URL`). The worker reconciles the same rewrite onto the
  production Amplify app, so `https://i2g.ucmerced.edu/api/...` also reaches
  production that way. Admin paths are proxied the same way on demo
  (`AMPLIFY_PROXY_ADMIN_PATHS=true`), not on production.
- When the `DJANGO_ALLOWED_HOSTS` variable is unset, the deploy adds
  `.cloudfront.net` and `.elb.amazonaws.com` to the allowed hosts. That permits
  a CloudFront distribution in front of the API but does not show that one
  exists.

Unknown from the repository (check in AWS and GitHub before creating rules):

- whether `api.i2g.ucmerced.edu` resolves to the ALB or to a CloudFront
  distribution (DNS is managed outside this repository);
- the production `VITE_API_BASE_URL` GitHub variable, which overrides the
  default above;
- whether a web ACL is already associated with the ALB, a CloudFront
  distribution or the Amplify app;
- which headers the Amplify rewrite forwards to the origin.

What follows:

| Path | Attach the rules to | Client IP WAF sees |
|------|---------------------|--------------------|
| Browser → ALB | `REGIONAL` web ACL on the ALB | The real client (the campus NAT address for campus users) |
| Browser → CloudFront/Amplify → ALB | `CLOUDFRONT` web ACL on that distribution, or Amplify Hosting's firewall integration for the Amplify app | The real client at the edge; the ALB sees only edge addresses shared by many users |

- If both paths are in use, attach rules at both. On the ALB, keep the
  off-campus rules in **COUNT** for as long as proxied traffic also reaches it:
  there, one "IP" is an edge server carrying many users.
- Do not use a `FORWARDED_IP` (X-Forwarded-For) aggregation key to work around
  this. WAF takes the first address in the header, which the client can write
  itself.

## 3. Endpoints in scope

Only unauthenticated `POST` endpoints. Authenticated endpoints are limited per
user in the application. `POST /authn/refresh/` is excluded because every
signed-in tab calls it. Health checks and `GET` status lookups are excluded too.
So are the newsletter links `/mail/unsubscribe/<token>/` and
`/mail/resubscribe/<token>/`: mailbox providers send the RFC 8058 one-click
`POST` from their own shared servers, so a per-IP limit would drop other
people's unsubscribes, and every request needs a signed token, changes only
that member's flags and sends at most one confirmation per real change.

**A. Credential and code checks** (guessing, and the CPU cost of RSA decrypts
and PBKDF2):

| Path | Purpose |
|------|---------|
| `/authn/login/` | Password sign-in (RSA decrypt + PBKDF2; identifier lockout in app) |
| `/authn/login/verify-code/`, `/authn/email-auth/verify-code/`, `/authn/register/verify-code/` | Email code verification |
| `/authn/phone-auth/verify-code/` | SMS code verification |
| `/authn/password-reset/verify-code/`, `/authn/password-reset/confirm/` | Password reset |
| `/mail/login-link/` (legacy `/mail/magic-login/`), `/authn/impersonate-login/` | Emailed-token exchanges |
| `/admin/login/` | Django admin sign-in (password and email code) |

**B. Sends** (mail/SMS bombing and challenge-table growth):

| Path | Purpose |
|------|---------|
| `/authn/send-verification/challenge/`, `/admin/send-verification/challenge/` | ALTCHA challenge issuance (writes a row, sends nothing) |
| `/authn/email-auth/request-code/`, `/authn/login/request-code/` | Email code |
| `/authn/register/`, `/authn/register/resend-code/` | Registration email |
| `/authn/password-reset/request-code/` | Reset code (email or SMS) |
| `/authn/phone-auth/request-code/` | SMS code |

**C. Anonymous writes** (request floods and table growth; the caller is
identified only by a value it mints itself):

| Path | Purpose |
|------|---------|
| `/analytics/pageview/` | Page-view tracking: one `analytics_pageview` row per accepted request, no retention. In the application: 120/minute per browser `visitor_id` (chosen by the client) and 3,000/minute in total per Uvicorn worker, above which page views are dropped |
| `/assistant/chat/` | Public assistant chat. Spend is bounded by the PostgreSQL token budgets, but the request rate is per visitor token and `GET /assistant/config/` hands a token to anyone. Every request costs a budget transaction, and a refused one still writes an audit-log row |

Neither of the two can be limited per client IP in the application (campus
visitors share one address), and their in-app throttles are fairness limiters
kept per process (see
[Environments](environments.md#the-throttle-cache-alias)). A flood from one
off-campus address is bounded here; a flood from campus only by the in-app
total page-view cap and the token budgets (section 7).

Through Amplify these paths carry an `/api` prefix at the edge and lose it at
the origin, so each pattern covers both. Create three regex pattern sets, one
per list (field: URI path; text transformations `URL_DECODE` then
`NORMALIZE_PATH`). **AWS WAF accepts at most 200 characters per regex pattern**
and at most 10 patterns per set, and a set matches when **any** of its patterns
matches, so lists A and B are split over two patterns each and C fits in one
(160, 79, 172, 45 and 47 characters):

```text
Pattern set A (credential and code checks)
A1: ^(/api)?/authn/(login|login/verify-code|email-auth/verify-code|register/verify-code|phone-auth/verify-code|password-reset/verify-code|password-reset/confirm)/?$
A2: ^(/api)?/(authn/impersonate-login|mail/(login-link|magic-login)|admin/login)/?$

Pattern set B (sends)
B1: ^(/api)?/authn/(send-verification/challenge|email-auth/request-code|login/request-code|register|register/resend-code|password-reset/request-code|phone-auth/request-code)/?$
B2: ^(/api)?/admin/send-verification/challenge/?$

Pattern set C (anonymous writes)
C1: ^(/api)?/(analytics/pageview|assistant/chat)/?$
```

Keep every pattern anchored (`^`, `$`) and at or under 200 characters; when a
list outgrows a pattern, add another pattern to the same set instead of
loosening one (an `/authn/` prefix would also rate-limit `/authn/refresh/` and
`/authn/session/`).

`apps/authn/tests/misc/test_waf_runbook_patterns.py` reads these five lines and
checks them against every route Django serves (`src/config/routing/urls.py`
and everything it includes): each listed path matches its own set, and no other
set, with and without `/api` and the trailing slash; no other route matches any
set (including `/authn/refresh/`, `/authn/session/` and
`/assistant/config/`); and no pattern exceeds the limits. Update the tables,
the patterns and that test together whenever these routes change.

## 4. Rules

Evaluation window 5 minutes, aggregation key `IP`, each with a scope-down of
`method = POST` AND the path pattern AND the campus condition:

| Priority | Rule | Paths | Campus condition | Action |
|----------|------|-------|------------------|--------|
| 1 | `campus-auth-count` | A or B | source IP **in** a campus set | **COUNT, permanently** |
| 2 | `offcampus-credential-rate` | A | source IP **not in** any campus set | COUNT, then BLOCK |
| 3 | `offcampus-send-rate` | B | source IP **not in** any campus set | COUNT, then BLOCK |
| 4 | `campus-anon-write-count` | C | source IP **in** a campus set | **COUNT, permanently** |
| 5 | `offcampus-anon-write-rate` | C | source IP **not in** any campus set | COUNT, then BLOCK |

Starting limits. These are **starting points only**, not measured values:
calibrate them from the COUNT metrics before any rule blocks.

| Rule | Starting limit (requests per IP per 5 minutes) | Reasoning |
|------|-----------------------------------------------|-----------|
| `campus-auth-count` | 1000 | One campus address carries everyone on campus; an event-registration rush of a few hundred sign-ins, each a few POSTs, stays near or under it. It only raises an alarm. |
| `offcampus-credential-rate` | 100 | A person signing in makes a handful of these; allows for carrier-grade NAT on mobile networks. |
| `offcampus-send-rate` | 30 | Each code request is a challenge plus a send; 30 allows about 15 code requests per address. |
| `campus-anon-write-count` | 5000 | Every page a campus visitor opens is one page-view `POST` from the same address. The estimated busiest campus minute is about 150 page views, about 750 per 5 minutes; 5000 is several times that. It only raises an alarm. |
| `offcampus-anon-write-rate` | 600 | Two requests a second, sustained, from one address. One browser sends one page view per page it opens and a few chat messages, and the in-app per-visitor rate (120/minute) admits no more than this for a single browser. A shared off-campus network (a sponsor's office, a conference venue) can legitimately exceed it. |

Set C has one limit for both paths because page views dominate it. A blocked
page view loses one analytics row and nothing the visitor can see (the frontend
ignores the answer). A blocked chat request shows the assistant's usage-limit
message, which the widget displays for any `429`. If the chat needs a tighter
limit than page views, split C into two single-path pattern sets with one
off-campus rule each.

For BLOCK, use a custom response, not WAF's default `403` (the login-link page
treats a `403` as a terminal failure):

| Part | Value |
|------|-------|
| Response code | `429` |
| Custom response body (content type `APPLICATION_JSON`) | `{"detail": "Too many requests. Please try again in a few minutes."}` |
| Header `Retry-After` | `300` |
| Header `Access-Control-Allow-Origin` | The exact frontend origin, for example `https://i2g.ucmerced.edu` (never `*`) |
| Header `Access-Control-Allow-Credentials` | `true` |
| Header `Access-Control-Expose-Headers` | `Retry-After` |

Why the three CORS headers: the production frontend
(`https://i2g.ucmerced.edu`) calls the API origin
(`https://api.i2g.ucmerced.edu`) cross-origin and with credentials. A WAF
custom response carries only the headers configured on it, and it never reaches
Django, so the application's CORS middleware cannot add them.

- **With them**, the page's script can read the response: the frontend handles
  the `429` as a retryable rate limit and forms show the `detail` sentence.
  `Access-Control-Expose-Headers` makes `Retry-After` readable to scripts too
  (it is outside the CORS safelist; the frontend does not read it today).
- **Without them**, the browser still receives the `429` but refuses to hand it
  to the page: the script sees a network error with no status, no body and no
  `Retry-After`. The login-link page treats it as a connection failure, and
  forms show "An unexpected error occurred. Please try again." A code request
  blocked after its ALTCHA challenge got through is worse: the page takes it
  for a send whose answer was lost, cannot find it on the server, and keeps
  reporting "The previous send request is still unresolved" for that
  destination for as long as the tab stays open, instead of asking the user to
  wait.

The allowed origin must be one literal origin (scheme and host, no path, no
trailing slash) because the request is credentialed; a wildcard is rejected by
the browser. A custom response names one origin only: a second frontend origin
calling the same API origin cross-origin would get the "without them"
behaviour, so give each API origin its own web ACL. On the Amplify path the
page calls `/api/...` on its own origin, so the CORS headers are not needed
there and do no harm. The rules match `POST` only, so the browser's `OPTIONS`
preflight is never blocked and is still answered by the application.

## 5. From COUNT to BLOCK

1. Enable WAF logging (a CloudWatch Logs group whose name starts with
   `aws-waf-logs-`) or at least sampled requests on every rule.
2. Run all five rules in COUNT for at least two weeks, including a peak: the
   start of a term and the opening of event registration.
3. During peaks, list the addresses over each limit with
   `aws wafv2 get-rate-based-statement-managed-keys`. Classify each: attacker,
   off-campus partner network (a sponsor's office NAT), or a campus range
   missing from the IP set (ask campus IT, then add it).
4. Set each off-campus limit to at least 3 times the highest legitimate
   per-address rate seen. A legitimate shared network that needs more gets its
   own IP set (ranges from that organisation's IT) excluded like the campus.
5. Switch `offcampus-credential-rate`, `offcampus-send-rate` and
   `offcampus-anon-write-rate` to BLOCK. Leave `campus-auth-count` and
   `campus-anon-write-count` in COUNT for good.
6. Rollback is one change with no deploy: set the rule action back to COUNT.

## 6. Alarms

WAF publishes `CountedRequests` and `BlockedRequests` per rule in the
`AWS/WAFV2` namespace (dimensions `WebACL` and `Rule`, plus `Region` for a
regional ACL; CloudFront-scope metrics are in `us-east-1`).

| Alarm | Condition | Response |
|-------|-----------|----------|
| Campus auth burst | `campus-auth-count` `CountedRequests` ≥ 1 in 5 minutes | Check whether it is an event rush or abuse from a campus machine. Never block the campus address; rely on the in-app limits and contact campus IT about a compromised host. |
| Campus anonymous-write burst | `campus-anon-write-count` `CountedRequests` ≥ 1 in 5 minutes | Check for a looping script or a compromised campus machine. Never block the campus address; the in-app total page-view cap and the assistant token budgets bound the damage. |
| Off-campus blocking | `BlockedRequests` on any off-campus rule above the calibrated baseline for 15 minutes | Check for a false positive (a new partner network) before assuming an attack. |

Pair them with the application alarms in
[Send verification: monitoring](send-verification.md#monitoring):
`login_guard.failure_spike` (password spraying, including from campus),
`send_verification.quota_sms_daily` (SMS budget exhausted) and the RDS
`FreeStorageSpace` alarm (the tables behind set C grow with request volume).
For set C the application also logs, at most once a minute per worker process:

- `analytics.pageview_total_cap` (WARNING, logger `apps.cms.views.analytics`):
  a worker reached 3,000 page views in a minute and is dropping the rest. A
  metric filter on that text is the signal that a page-view flood got past the
  edge, or came from campus.
- `Assistant global token budget exhausted` (WARNING): model calls are refused
  until the window ends or the limit is raised (see
  [Assistant and AI search limits](../integrations/assistant-limits.md)).

## 7. Not covered

- **Attacks from campus addresses.** Only the in-app controls apply: the
  per-identifier lockout, per-destination quotas and cooldowns, ALTCHA in
  `enforce` mode, code-guess degradation, and the spray alarm.
- **Distributed attacks** (many addresses, each under the limit). Per-IP rules
  cannot see them; the in-app per-identifier and per-destination limits still
  hold.
- **Floods of set C from campus or from many addresses.** Only the in-app
  bounds apply. Page views: 3,000 a minute per Uvicorn worker in total, above
  which analytics rows are dropped and nothing user-facing is blocked.
  Assistant: the per-visitor and global token budgets bound spend; they do not
  bound request count, and each refused request still writes an audit-log row
  while audit logging is on. Watch the RDS free-storage alarm.
- **Client-IP handling inside the application** (`NUM_PROXIES`,
  `X-Forwarded-For`; see
  [Client IP and proxy trust](backend.md#client-ip-and-proxy-trust)) is separate
  work and does not change these rules.

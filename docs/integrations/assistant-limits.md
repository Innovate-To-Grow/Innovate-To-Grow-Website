# Assistant and AI search limits

How the public assistant (`/assistant/`) and the past-project AI search
(`POST /projects/past-ai-search/`) are rate-limited and how their Amazon Bedrock
spend is bounded. Nothing here is keyed on the client IP: campus users share one
public address, so an IP bucket would be one bucket for the whole campus.

## Who a limit is keyed on

| Actor | Who | How it is recognised |
|-------|-----|----------------------|
| Member | A signed-in member. AI search always (it requires sign-in); the chat only if a caller authenticates, which the SPA does not do (its shared `api` client sends no `Authorization` header) | Member id |
| Visitor | One anonymous browser | A server-signed, stateless `visitor_token` (128-bit random id, signed with `SECRET_KEY`) |
| Legacy | Everyone without a valid token: frontend bundles cached before the token existed, scripts, expired or forged tokens | **One shared actor** for all of them (see [The legacy actor](#the-legacy-actor)) |

Budget rows and throttle keys hold only a keyed hash of the actor
(`services/public_assistant/actors.py`); the client IP is recorded as `ip_hash`
in the conversation log for audit and keys no limit.

### Visitor token contract

- `GET /assistant/config/` returns `visitor_token` while the assistant is enabled
  (omitted when disabled) and is served with `Cache-Control: no-store`. The
  widget stores it in `localStorage` (`itg-assistant-visitor`) only when it
  holds none, so a reload keeps one identity (and one budget).
- `POST /assistant/chat/` accepts an optional `visitor_token` in the JSON body
  (not a header, so the CORS allow-list is unchanged). A missing, malformed,
  expired or forged token is **never rejected**: the request is answered as the
  legacy actor.
- Any chat response may carry a replacement `visitor_token` for the client to
  store: `200`, `413`, `429` (budget and the framework's throttled `429`, whose
  body is then `{"detail": "...", "visitor_token": "..."}`), `502` and `503`.
  The widget stores it and, when a `429` handed it one, re-sends the message
  once with the new token.
- A token is honoured for 30 days and re-signed (same id, same budget) once it
  is older than 15 days.

### The legacy actor

Every request without a valid token is the same single actor, whatever its IP
address, so inventing token values never buys a caller a bucket of their own.
That one actor stands for many people at once (every tab still running an old
bundle), so it is treated differently from a visitor:

- It is **exempt from the per-visitor token limit**. One visitor's allowance
  would be used up by the first couple of dozen answers of the day for all
  old-bundle users together, and it would protect nothing: any caller can get a
  visitor token, and with it a full allowance, from `GET /assistant/config/`.
- It is bounded by its own request rate (60/minute, see
  [Request rates](#request-rates)) and by the **public assistant's global token
  budget**, the same ceiling that bounds every visitor.
- Its usage is still counted, in one budget row of its own.

**Deploy order.** Either order works: an old backend ignores the field and a new
backend answers token-less requests. Until the new frontend is live (and for
tabs still running an old bundle) SPA visitors are the legacy actor: they keep
being answered while the assistant's global budget has room, up to 60 requests a
minute per Uvicorn worker process in total, and no limit has to be raised for the rollout.
Deploying the frontend first or together with the backend is still preferable,
because only a browser with a token gets its own 6/minute rate and its own token
allowance. The two global budget rows need no data migration: each is created by
the first request of its feature.

## Request rates

| Throttle | Rate | Key |
|----------|------|-----|
| `PublicAssistantActorThrottle` (`POST /assistant/chat/`) | 6/minute (`public_assistant`) | Visitor or member |
| same, legacy actor | 60/minute (`public_assistant_legacy` in `DEFAULT_THROTTLE_RATES` overrides the built-in default) | One shared bucket |
| `PastProjectAISearchRateThrottle` (`POST /projects/past-ai-search/`) | 10/minute (`past_project_ai_search`) | Member |

These are fairness limits. The assistant throttle's history is in the bounded
in-process `throttle` cache alias (visitor tokens are free to mint, so it is
kept out of the file cache; see
[Production cache today](../deployment/environments.md#production-cache-today)),
so its effective rate is the nominal rate times the number of Uvicorn worker
processes (`WEB_CONCURRENCY` x ECS tasks). The AI search throttle is per member
in the default per-container cache. Money does not depend on either.

## Token budgets

Every model call reserves `estimated input + maximum output` tokens against two
budgets in one transaction, is admitted only if it fits **both**, and is
reconciled to the provider's actual usage afterwards (released entirely if the
call fails):

1. the **actor's** budget (a visitor or a member; the legacy actor's row is
   charged but has no limit), and
2. the **global budget of the feature being used**. There are two global rows,
   one for the public assistant and one for AI search. Each is limited by the
   same admin value, each has its own 24-hour window, and a request is only
   ever charged to its own feature's row.

The counters are rows of `PublicAssistantTokenBudget` in PostgreSQL (Redis
instead when `REDIS_URL` is set), so every worker and ECS task shares them and
concurrent requests cannot overspend. A request locks its feature's global row
first and then the actor row, always in that order.

Both limits are fields of the active **System Intelligence Config** (Django
admin → System Intelligence → Assistant Tools → Assistant Settings, "Public
Assistant" section). A change applies to the next request; no deploy.

| Admin field (model field) | Default | Bounds |
|---------------------------|---------|--------|
| Per-Visitor / Per-Member Token Limit (`public_assistant_ip_token_limit`) and Window (`public_assistant_ip_token_window_seconds`) | 50,000 per 86,400 s | One visitor or one member, across the assistant and AI search. The legacy actor is exempt. `0` disables it. The column names are historical; nothing is per IP |
| Global Token Limit (per feature, per 24 hours) (`public_assistant_global_token_limit`) | 2,000,000 | **Each feature separately, for everyone**: the assistant may use up to this many tokens per 24 hours and AI search may use up to this many. A feature's window opens with its first request after its previous one ended. `0` switches off the model calls of both features |

Visitor tokens are free to obtain (every `GET /assistant/config/` mints one), so
the per-visitor limit is a fairness limit only. **The global limit is the spend
bound**, and a feature's budget can be exhausted by abuse or by a busy day. The
two rows are separate so that the anonymous chat, which a script can drain with
freshly minted tokens, cannot switch off the signed-in members' AI search (or
the other way round). When a feature's budget is spent:

- that feature answers `429` with `code: "budget_exceeded"`: the assistant with
  "The assistant has reached its usage limit for now. Please try again later.",
  AI search with "AI search has reached its usage limit for now. Please try
  again later.";
- it stays paused until its window ends or the limit is raised in admin;
- **the other feature keeps working**, on its own counter;
- nothing else is affected: sign-in, registration, events, the project catalog
  and the admin assistant do not use these budgets.

`503` with `code: "budget_unavailable"` means the budget store could not be
reached (both endpoints fail closed rather than spend unaccounted tokens).

### Usage in admin

Right below the Global Token Limit field, the same admin form shows **Global
Tokens Used (current window)**, read-only, one line per feature:

```
Public assistant: 1,234,567 of 2,000,000 tokens (61%) · window ends 2026-10-02 09:30 PDT
AI search: 45,000 of 2,000,000 tokens (2%) · window ends 2026-10-02 11:05 PDT
```

The figures are read when the page loads and include tokens reserved by calls
still in flight. "no window open" means nothing has been charged to that feature
since its last window ended. The counters are site-wide: on a config that is
not active the form says so, because the active config's limit is the one
enforced.

### Sizing the global limit

Measured token cost per request (input estimate plus output cap):

| Request | Tokens |
|---------|--------|
| Chat answer, typical site context | about 2,700 (1,685 input + up to 1,024 output) |
| Chat answer, context at the 24,000-character cap | about 7,300 |
| AI search over a broad candidate list | about 15,000 |

The limit is one number that applies to each feature on its own, so size it for
the busier one.

1. Peak-day tokens, per feature, for the busiest expected day (an event day, a
   class using the assistant at once):
   assistant = `people x questions per person x tokens per answer`;
   AI search = `searches x 15,000`.
2. Set the limit to at least **2 x** the larger of the two, so honest traffic
   never reaches it.
3. **Expected daily cost at a typical mix** =
   `tokens used x (0.85 x P_in + 0.15 x P_out) / 1,000,000`, where `P_in` and
   `P_out` are the Amazon Bedrock prices per million input and output tokens of
   the configured model (Public Assistant Model, else the default model) from
   the [Bedrock price list](https://aws.amazon.com/bedrock/pricing/). Requests
   are mostly input (context and history), hence the 85/15 split. This is an
   estimate of what a day costs, not a bound.
4. **Ceiling per 24-hour window** = `limit x P_out / 1,000,000` **per feature**,
   so `2 x limit x P_out / 1,000,000` for both. It prices every token at the
   output rate (the more expensive one), which no real request reaches, so
   actual spend stays below it. A feature's window opens with its first charge
   and is not aligned to the calendar, so around a window boundary up to twice
   the limit can be spent within one calendar day (the end of one window and the
   start of the next); the monthly figure is unaffected. (A call is admitted on its estimate and reconciled to
   actual usage, so a window can end above the limit by the difference between
   estimate and actual usage of the calls that were in flight.) Monthly ceiling
   = 30 x the window ceiling.

Example, at illustrative prices of $3 input and $15 output per million tokens:

- Peak day: assistant 200 visitors x 3 questions x 2,700 = 1,620,000 tokens;
  AI search 20 searches x 15,000 = 300,000 tokens. The larger is 1,620,000, and
  2 x 1,620,000 = 3,240,000, so set about 4,000,000.
- Expected cost of that peak day at the typical mix (0.85 x 3 + 0.15 x 15 =
  $4.80 per million): (1,620,000 + 300,000) x 4.80 / 1,000,000 = $9.22.
- A feature that used its whole 4,000,000 at the typical mix would cost
  4,000,000 x 4.80 / 1,000,000 = $19.20 that day. A caller who always asks for
  the longest answers reaches about a 38% output share (1,024 of 2,709 tokens),
  which is 0.62 x 3 + 0.38 x 15 = $7.56 per million, or $30.24.
- Ceiling: 4,000,000 x 15 / 1,000,000 = **$60 per 24-hour window, per feature**,
  $120 per window for both, and 30 x 120 = $3,600 a month if both features hit
  it in every window.

The default 2,000,000 covers about 740 typical chat answers and, separately,
about 133 broad AI searches per 24 hours; its ceiling is 2,000,000 x 15 /
1,000,000 = $30 per 24-hour window, per feature, at those prices. If the ceiling is
unacceptable, lower the limit, shorten the context, or choose a cheaper model
rather than adding a per-IP limit.

### Alarm

When a feature's global budget refuses a request, the logger
`apps.system_intelligence.services.public_assistant.budget` writes one WARNING,
at most once a minute per feature and container:

```
Assistant global token budget exhausted for Public assistant (limit 2000000 per 86400s): ...
Assistant global token budget exhausted for AI search (limit 2000000 per 86400s): ...
```

Create a CloudWatch Logs metric filter and alarm on it, the same way as the
sign-in alarms in [Send verification: Monitoring](../deployment/send-verification.md#monitoring):

```bash
aws logs put-metric-filter \
  --log-group-name /ecs/itg-backend \
  --filter-name assistant-global-budget-exhausted \
  --filter-pattern '"global token budget exhausted"' \
  --metric-transformations metricName=AssistantGlobalBudgetExhausted,metricNamespace=I2G/Assistant,metricValue=1,defaultValue=0
```

That pattern matches both features; use `"global token budget exhausted for AI
search"` (or `for Public assistant`) for a per-feature alarm.

The line fires only once a budget is spent. For an early warning, check
[Usage in admin](#usage-in-admin), or alarm on the `AWS/Bedrock`
`InputTokenCount` + `OutputTokenCount` daily sum at about 80% of the limit (that
metric adds both features together and also includes the admin assistant, which
these budgets do not cover). The [usage dashboard](system-intelligence-usage.md)
charts the same metrics.

Expired budget rows are deleted by the background worker's hourly maintenance
(`purge_expired_public_assistant_budgets`).

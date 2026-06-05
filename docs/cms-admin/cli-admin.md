# i2g-admin CLI

A terminal CLI for remote record management of the deployed backend, **without** API keys or any long-term secret. The CLI rides the **existing staff admin login**: it opens the browser to the backend admin, you log in normally, and an OAuth2 **Authorization Code + PKCE** exchange turns that completed login into a short-lived bearer token used for generic CRUD over the `/admin-api/` REST surface.

- **Client package**: `cli/` (repo root), installs the `i2g-admin` command.
- **Backend app**: `src/apps/cli_admin/`, mounted at `/admin-api/`.
- **Audience**: staff/operators who need quick read/write access to records from a terminal, and engineers maintaining the admin API.

Access requires the logged-in account be `is_active` **and** `is_staff`. There are **no per-model Django permission checks** — staff status is the gate, backed by a hard denylist. Writes apply immediately and are audit-logged.

## How authentication works

The CLI never scrapes admin HTML; it uses the admin login *only* to authenticate, then does CRUD via `/admin-api/`.

```
i2g-admin login
  └─ bind 127.0.0.1:0 (one-shot callback server)  redirect_uri = http://127.0.0.1:<port>/callback
  └─ open browser → GET /admin-api/oauth/authorize/?response_type=code&client_id&redirect_uri
                          &code_challenge&code_challenge_method=S256&state
        ├─ not logged-in staff → 302 /admin/login/?next=<authorize URL> → (admin logs in) → back
        └─ valid params → create single-use authorization code (sha256-hashed) → 302 redirect_uri?code&state
  └─ callback server receives code+state → verify state (constant-time)
  └─ POST /admin-api/oauth/token/ {grant_type, code, code_verifier, redirect_uri, client_id}
        ├─ claim the code atomically (single-use) BEFORE other checks
        ├─ constant-time compare redirect_uri → verify PKCE S256 → re-check is_active & is_staff
        └─ mint bearer token → {access_token, token_type:"Bearer", expires_in}
  └─ save token to ~/.config/i2g-admin/credentials.json (0600)
```

Security properties baked into the flow:

| Concern | Mitigation |
|---|---|
| Authorization-code replay | Codes are single-use (atomic claim before any other check) and expire after **60s**; stored sha256-hashed |
| PKCE downgrade | Only `S256` is accepted at both authorize and token; `plain` is rejected |
| Open redirect | `redirect_uri` must be `http` on a loopback IP (`127.0.0.1`/`::1`) with a `/callback` path — no credentials, query, or fragment |
| Token endpoint CSRF | No cookies/session — auth is `code + code_verifier` only |
| Staff drift / revocation | `is_active` and `is_staff` are re-checked on every request; tokens can be revoked from the admin; default TTL is **8h** (no refresh — re-login on expiry) |
| Token at rest | Codes and tokens are stored sha256-hashed server-side; the raw token lives only in transit and in a `0600` file; never passed via argv or env |

## Installation

```bash
cd cli && pip install -e .          # installs the `i2g-admin` command (Python 3.11+)
```

The client depends only on `typer`, `requests`, and `rich`; it is packaged separately so its dependencies never touch the backend.

## Configuration

The CLI has **no baked-in backend URL** — there is no hardcoded production default. The base URL is resolved, in order, from:

1. the active profile's stored `base_url` (set via `configure set base_url <url>`, kept in `config.json`),
2. the legacy `credentials.json`'s `base_url` (for the `default` profile),
3. the `I2G_ADMIN_BASE_URL` environment variable, or a `.env` file (copy `cli/.env.example` to `cli/.env`).

If none is set, the command fails with a clear configuration error rather than silently targeting a default host.

```bash
i2g-admin configure set base_url http://127.0.0.1:8000   # persist for the active profile (preferred)
i2g-admin configure get base_url                          # print the resolved value
i2g-admin configure list                                  # known profiles + the active default
i2g-admin configure --base-url http://127.0.0.1:8000      # back-compat: same as `set base_url`
i2g-admin configure                                       # back-compat: persist the env/.env value
```

- For safety, the base URL **must be `https`** — `http` is only allowed for loopback hosts (`127.0.0.1` / `localhost` / `::1`), so a bearer token is never sent in cleartext to a remote host.
- Credentials are cached at `${XDG_CONFIG_HOME:-~/.config}/i2g-admin/credentials.json` with `0600` permissions (directory `0700`), holding `{base_url, access_token, expires_at}`.

### Profiles

Like the AWS CLI, you can keep several named environments. Pass `--profile <name>` **before the command** (or set `I2G_ADMIN_PROFILE`):

```bash
i2g-admin --profile staging configure set base_url http://127.0.0.1:8000
i2g-admin --profile staging login
i2g-admin --profile staging records list projects Semester
```

- Per-profile settings (currently `base_url`) live in `${XDG_CONFIG_HOME:-~/.config}/i2g-admin/config.json` under `profiles.<name>`, alongside `default_profile`.
- The `default` profile reuses the legacy `credentials.json`; a named profile uses `credentials-<name>.json` (all `0600`).
- Profile names are restricted to letters, digits, `.`, `_`, and `-` so a name can never escape the config directory.

## Global options

Modeled on the AWS CLI, the cross-cutting options live on the **root** and must be placed **before** the command (as in `aws --output json s3 ls`):

```bash
i2g-admin --profile staging --output json records list projects Semester
```

| Option | Default | Purpose |
|---|---|---|
| `--profile <name>` | `default_profile` from `config.json` | Select a named configuration/credentials profile (also `I2G_ADMIN_PROFILE`). |
| `--output table\|json\|text\|yaml\|csv` | `table` | Output format. |
| `--query <expr>` | — | Client-side JMESPath projection of the result. |
| `--no-paginate` | off | Disable automatic pagination (`records list` walks all pages by default). |
| `--max-items <n>` | — | Stop after this many items when paginating. |
| `--page-size <n>` | — | Items to request per page when paginating (capped at the server max of 50). |
| `--max-attempts <n>` | `1` | Max HTTP attempts; transient `429/5xx` are retried with exponential backoff + jitter, honoring `Retry-After`. |
| `--connect-timeout <s>` | `5` | Per-request connect timeout (seconds). |
| `--read-timeout <s>` | `30` | Per-request read timeout (seconds). |
| `--debug` | off | Emit extra detail (the error `repr`) on failures. |
| `--version` | — | Print the version and exit. |

The per-command `--json` flag is a back-compat alias for `--output json`.

## Commands

| Command | Description |
|---|---|
| `configure set <key> <value>` | Set a config value (currently `base_url`) for the active profile |
| `configure get <key>` | Print a resolved config value |
| `configure list` | List known profiles and the active default |
| `configure [--base-url URL]` | Back-compat: persist the base URL for the active profile |
| `login` | Browser login → cache a short-lived token |
| `logout` | Delete the locally cached token for the active profile |
| `whoami` | Show the authenticated member and token expiry |
| `models` | List models readable/writable through the API |
| `schema <app> <model>` | Show readable/writable fields for one model (verbose name, help text, default, choices-with-labels, FK target) |
| `records list <app> <model>` | List records (filters, ordering, fields, paging; auto-paginates by default) |
| `records get <app> <model> <pk>` | Fetch one record |
| `records create <app> <model> --data <json>` | Create a record |
| `records update <app> <model> <pk> --data <json>` | Update a record |
| `records delete <app> <model> <pk>` | Delete a record (interactive confirm) |
| `records count <app> <model>` | Count matching records without fetching them |
| `records wait <app> <model> --until field=value` | Poll until a record reaches a target state |
| `apps` | List the apps exposed through the admin API |
| `completion show <shell>` | Print a shell completion script (plus Typer's built-in `--install-completion`/`--show-completion`) |

```bash
i2g-admin login
i2g-admin whoami
i2g-admin models
i2g-admin schema projects Semester
i2g-admin records list projects Semester --filter year=2025 --order -year --limit 20
i2g-admin records get projects Semester <pk>
i2g-admin records create projects Semester --data '{"year": 2026, "season": 1}'
i2g-admin records update projects Semester <pk> --data @changes.json
i2g-admin records delete projects Semester <pk> --confirm-cascade
i2g-admin logout
```

- `--data` accepts inline JSON, `@file.json`, or `@-` to read JSON from stdin.
- `--json` prints machine-readable JSON; otherwise results render as Rich tables (equivalent to `--output json`).
- `records list` flags: `--filter key=value` (repeatable), `--order field` / `--order -field` (repeatable), `--field name` (repeatable, restricts columns), `--limit` (capped at 50), `--offset`.
- `records delete` prompts for confirmation unless `--yes`; cascading deletes additionally require `--confirm-cascade`.

### Generate / pre-fill a payload

`records create` / `records update` support `--generate-cli-skeleton` (print an empty JSON template for the model so you can fill it in) and `--cli-input-json <json|@file>` (submit a previously generated/edited skeleton), mirroring the AWS CLI's skeleton workflow. You may still supply the body directly with `--data`; provide exactly one of `--data` / `--cli-input-json`.

## What you can and cannot touch

Reachability is decided by a shared denylist (used by both this CLI and the AI action engine) plus a CLI-specific extra denylist. Run `i2g-admin models` to see exactly what is readable and which models are writable.

**Models that are never reachable from the CLI:**

- The whole **`authn`** app (identity/auth): `Member`, `ContactEmail`, `RSAKeypair`, `EmailAuthChallenge`, etc. Manage identity and auth records through the Django admin UI instead — a writable identity model on a no-per-model-permission API is an account-takeover vector.
- Django internals: `admin.LogEntry`, `sessions.Session`, `contenttypes`, the stock `auth` app (`Group`/`Permission`).
- Anything matching a denied name part — `*credential*`, `*config*`, `*permission*`, `*session*`, `*token*`, `logentry`.
- Service configs and AI/chat models (`core.AWSCredentialConfig`, `system_intelligence.ChatMessage`, …), CMS structure (`cms.CMSPage`, `cms.CMSBlock`).
- The CLI's own tables (`cli_admin.*`) and other auth-sensitive tables (`mail.MagicLoginToken`, `authn.AdminInvitation`).

**Fields that are never writable** (even on otherwise-writable models): `password`, `*secret*`, `*token*`, `*api_key*`, `is_staff`, `is_superuser`, `groups`, `permissions`, plus primary keys and non-editable / auto-timestamp fields.

> The denylist lives in `src/apps/core/services/db_tools/safe_orm/`; the CLI's extra app/model denylist is `CLI_EXTRA_DENIED_APP_LABELS` / `CLI_EXTRA_DENIED_MODEL_LABELS` in `src/apps/cli_admin/constants.py`.

## Writes, cascades, and concurrency

- **Create / update** run `full_clean()` before saving; invalid data returns `400`.
- **Optimistic concurrency** — supply the `X-Expected-Snapshot` header (the JSON you previously read) on an update/delete; if the row changed since, the request fails with `409` instead of clobbering.
- **Cascade safety** — a delete that would remove related rows is refused with `400` unless `--confirm-cascade` is given; the cascade impact is reported and recorded.
- Every write attempt — success or failure — is recorded in the audit log.

## The `/admin-api/` surface (reference)

All endpoints except the OAuth pair require `Authorization: Bearer <token>`. A SimpleJWT access token is **rejected** here.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin-api/oauth/authorize/` | Session-auth authorize endpoint (PKCE) |
| `POST` | `/admin-api/oauth/token/` | Code → bearer token exchange (no auth/cookies) |
| `GET` | `/admin-api/whoami/` | Authenticated member + token expiry |
| `GET` | `/admin-api/apps/` | App list (backs `apps`) |
| `GET` | `/admin-api/models/` | Readable/writable model list |
| `GET` | `/admin-api/models/<app>/<model>/schema/` | Field schema (name, type, required, choices, plus verbose name, help text, default, FK target) |
| `GET` `POST` | `/admin-api/records/<app>/<model>/` | List / create (`?count=1` returns just the count) |
| `GET` `PATCH` `DELETE` | `/admin-api/records/<app>/<model>/<pk>/` | Retrieve / update / delete |

Status codes: `400` invalid input / denied model / bad filter value, `401` missing/expired/revoked token, `404` unknown record, `409` integrity error or stale snapshot, `429` throttled.

Per-view scoped throttles (rates in `src/config/settings/components/integrations/api.py`):

| Scope | Rate | Applies to |
|---|---|---|
| `cli_oauth` | 30/min (per IP) | Token exchange |
| `cli_read` | 120/min (per member) | Reads |
| `cli_write` | 60/min (per member) | Writes |

## Operations

### Auditing

Every write is recorded in `CliAuditLog` (actor, action, model, target, the denylist-filtered change set, before-snapshot, cascade summary, error, and request IP). View it in **Django admin → CLI Admin → Audit Log**.

> Audit payloads are filtered by the field-*name* denylist, which removes obviously sensitive fields. A secret stored in an unrecognized field name or inside a JSON/text value is not value-scrubbed — treat audit rows as least-privilege data.

### Revoking a token (kill switch)

In **Django admin → CLI Admin → Access Tokens**, select tokens and run **"Revoke selected tokens"**. Revocation takes effect on the token's next request. `i2g-admin logout` only clears the local copy.

### Cleaning up expired rows

```bash
cd src && python manage.py cli_admin_cleanup
```

Deletes expired authorization codes and expired/revoked access tokens. Run it on a schedule (cron or a periodic task) in production.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `token expired or invalid. Run 'i2g-admin login'` | The 8h token expired or was revoked — log in again |
| `base_url must be https, or http on a loopback host` | Set an `https` URL (or loopback `http` for local dev) |
| `OAuth state mismatch; aborting` | The browser callback's `state` didn't match — re-run `login`; do not reuse a stale browser tab |
| `Write/Read access is not allowed for authn.Member` (or similar) | Identity/auth models are intentionally off-limits to the CLI — use the Django admin UI |
| Delete returns `400` mentioning cascade | The delete would remove related rows — re-run with `--confirm-cascade` |
| Update returns `409` | The row changed since your `X-Expected-Snapshot` — refetch and retry |

## Related pages

- [Django Admin](django-admin.md) — Admin theme and navigation (the CLI Admin sidebar group lives here)
- [Operations](operations.md) — Other management commands and operational tasks
- [API: Routing Overview](../api/routing-overview.md) — Where `/admin-api/` sits among the route groups
- [Architecture: Backend](../architecture/backend.md) — App structure and the shared safe-ORM layer

---
name: cli-admin
description: Use when doing remote CRUD on backend records from the terminal with the i2g-admin CLI, or when working on the CLI client (cli/) or its backend (src/apps/cli_admin/, mounted at /admin-api/). Covers install, the OAuth2 + PKCE login, the record commands, the staff-only denylist, and the CLI's separate pytest runner.
---
# i2g-admin CLI (client `cli/` + backend `apps/cli_admin`)

A terminal CLI for staff to do generic record CRUD against the deployed backend **without** API
keys. It reuses the existing staff admin login: `i2g-admin login` opens the browser, you log in
normally, and an OAuth2 **Authorization Code + PKCE** exchange mints a short-lived bearer token
used against the `/admin-api/` REST surface.

**Authoritative reference:** [`docs/cms-admin/cli-admin.md`](../../../docs/cms-admin/cli-admin.md)
— read it for the full auth flow, security properties, denylist, and `/admin-api/` table. This
skill is the quick entry point; do not duplicate that doc.

## Two halves

- **Client** — `cli/` (repo root), a standalone Python package installing the `i2g-admin`
  command (deps: `typer`, `requests`, `rich`). It has **its own pytest suite** — not Django's runner.
  Layout under `cli/src/i2g_admin/`:
  - `app.py` — the Typer root: defines the `--profile/--output/--query/--no-paginate/--max-items/`
    `--page-size/--max-attempts/--connect-timeout/--read-timeout/--debug/--version` **global options**
    on the root callback (they go *before* the command, AWS-style), builds the shared `Context`, then
    calls `commands.register(app)`.
  - `commands/` — one module per command group (`auth`, `meta`, `records`, …), each exposing
    `register(app)`; `commands/__init__.py` is the single wiring point with numbered extension anchors.
  - `runtime.py` — the **leaf glue** (`_client`, `_execute`, `_load_data`, `current_profile`,
    `_current_context`). Command modules import this, **not** `app` — that breaks the `app`↔`commands`
    import cycle. `app.py` re-exports the same symbols for back-compat callers/tests.
  - `context.py` — the per-invocation `Context` dataclass + `build_client`.
  - `config.py` — profiles (`config.json` + per-profile `credentials-<name>.json`), `base_url`
    resolution, `.env` loading. No hardcoded backend URL.
  - `output.py` + `formatters/` — the `--output` pipeline (`json`/`table` live; `text/yaml/csv` are
    registered stubs); `query.py` — the `--query` JMESPath seam (passthrough/stub until that unit lands).
- **Backend** — `src/apps/cli_admin/` (DRF), mounted at `/admin-api/` in `src/config/urls.py`.
  Authenticates with the minted bearer token only; a SimpleJWT access token is **rejected** here.

## Install & use (client)

```bash
cd cli && pip install -e .                                # installs `i2g-admin` (Python 3.11+)
i2g-admin configure set base_url http://127.0.0.1:8000    # no baked-in default; https required off-loopback
i2g-admin login                                           # browser → admin login → 8h token at ~/.config/i2g-admin/ (0600)
i2g-admin models                                          # what's readable/writable
i2g-admin --profile staging records list projects Semester --filter year=2025 --order -year --limit 20
i2g-admin --output json records update projects Semester <pk> --data @changes.json
```

The CLI has **no baked-in backend URL** — set it via `I2G_ADMIN_BASE_URL` (env or `cli/.env`) or
`configure set base_url <url>`. Profiles: `--profile <name>` / `I2G_ADMIN_PROFILE`, `configure get/set/list`.
Global options (`--profile/--output/--query/--no-paginate/--max-items/--page-size/--max-attempts/`
`--connect-timeout/--read-timeout/--debug/--version`) go **before** the command. `--json` is a
per-command alias for `--output json`. `--data` takes inline JSON, `@file.json`, or `@-` (stdin).
Command surface (some delivered incrementally, with clear "not available in this build yet" errors
until the relevant unit lands): `configure`, `login/logout/whoami`, `models`, `schema`, `apps`,
`records list/get/create/update/delete/count/wait`, `completion`. See the authoritative doc for the
full table and per-option status.

## Testing

```bash
cd cli && PYTHONPATH=src python -m pytest -p no:cacheprovider           # client suite (NOT manage.py test)
cd cli && PYTHONPATH=src pytest --cov                                   # same suite with coverage
cd src && python manage.py test apps.cli_admin --settings=config.settings.local   # backend suite (Django runner)
```

The client suite imports `i2g_admin` from `cli/src/`, so run it with `PYTHONPATH=src` (or after
`pip install -e .`). Team bar: **100% per-app coverage** on the `cli/` client too — add client tests
for every new path. CI separately enforces **100%** on the **backend** `apps.cli_admin` (+ the shared
`safe_orm` service) via `manage.py test` (`--fail-under=100`), stricter than the 40% floor elsewhere.
The `cli/` client pytest suite is **not** wired into CI (its `pyproject.toml` sets no `fail_under`),
so run it locally and treat the backend suite as the CI-gated one — add backend tests for every new path.

## When developing the backend, preserve these invariants

- **Staff gate only.** Access requires `is_active` **and** `is_staff`, re-checked on every request;
  there are no per-model Django permissions. So reachability is enforced by denylists, not perms.
- **Denylists, not allowlists of trust.** A model/field is reachable unless denied. The shared
  denylist lives in `src/apps/core/services/db_tools/safe_orm/` (also used by the AI action engine);
  the CLI's extra app/model denylist is `CLI_EXTRA_DENIED_*` in `src/apps/cli_admin/constants.py`.
  The whole `authn` app, anything matching `*credential*`/`*config*`/`*token*`/`*session*`/
  `*permission*`, and fields like `password`/`is_staff`/`*secret*` are never reachable/writable —
  loosening this on a no-per-model-permission API is an account-takeover vector.
- **PKCE `S256` only**; auth codes are single-use (atomic claim first) + 60s; tokens default 8h, no
  refresh, revocable from admin. Store codes/tokens sha256-hashed; never log raw tokens.
- **Writes:** `full_clean()` before save (`400` on invalid); optimistic concurrency via
  `X-Expected-Snapshot` (`409` on stale); cascading deletes refused with `400` unless confirmed;
  every write (success or failure) is recorded in `CliAuditLog`.
- Cleanup of expired codes/tokens: `cd src && python manage.py cli_admin_cleanup` (run on a schedule in prod).

## Key files

- `cli/README.md`, `cli/CHANGELOG.md`, `cli/pyproject.toml` — client package + `i2g-admin` entrypoint (version also in `cli/src/i2g_admin/__init__.py`)
- `cli/src/i2g_admin/app.py` — Typer root + global options; `commands/` — command groups; `runtime.py` — leaf glue
- `cli/src/i2g_admin/config.py` / `context.py` / `output.py` / `formatters/` / `query.py` — profiles, context, output pipeline, format/query seams
- `cli/.env.example` — copy to `cli/.env`; sets `I2G_ADMIN_BASE_URL` (no hardcoded prod URL)
- `cli/tests/` — client pytest suite (incl. `conftest.py`); run with `PYTHONPATH=src`
- `src/apps/cli_admin/urls.py`, `views/`, `authentication.py`, `pkce.py`, `permissions.py`, `throttles.py`
- `src/apps/cli_admin/constants.py` — CLI extra denylist
- `src/apps/core/services/db_tools/safe_orm/` — shared model/field denylist
- `src/config/settings/components/integrations/api.py` — `cli_oauth`/`cli_read`/`cli_write` throttle rates
- `docs/cms-admin/cli-admin.md` — authoritative reference

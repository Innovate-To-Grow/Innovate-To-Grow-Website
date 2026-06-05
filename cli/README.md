# i2g-admin

A terminal CLI for remote record management of the Innovate-To-Grow backend.

It rides the **existing staff admin login**: `i2g-admin login` opens the browser to
the backend admin, you log in normally, and an OAuth2 **Authorization Code + PKCE**
exchange turns that completed login into a short-lived bearer token. The token is
cached in a `0600` file under `~/.config/i2g-admin/` and used for generic CRUD over
the backend's `/admin-api/` REST surface. No API keys, no long-term secrets.

## Install

```bash
cd cli && pip install -e .
```

## Configuration

The CLI has **no baked-in backend URL** — set it via the environment, a `.env`
file, or `configure`. Resolution order: `--profile`'s stored `base_url` →
`I2G_ADMIN_BASE_URL` env / `.env` → error.

```bash
i2g-admin configure set base_url http://127.0.0.1:8000   # persist for the active profile
i2g-admin configure get base_url                          # print the resolved value
i2g-admin configure list                                  # known profiles + default
```

### Profiles

Like the AWS CLI, you can keep several named environments. Pass `--profile`
(or set `I2G_ADMIN_PROFILE`) before the command:

```bash
i2g-admin --profile staging configure set base_url http://127.0.0.1:8000
i2g-admin --profile staging login
```

The `default` profile reuses the legacy `~/.config/i2g-admin/credentials.json`;
named profiles use `credentials-<name>.json` (all `0600`).

## Usage

```bash
i2g-admin login                                        # browser → admin login → token cached
i2g-admin whoami
i2g-admin models
i2g-admin schema event Event
i2g-admin records list projects Semester --filter year=2025 --order -year --limit 20
i2g-admin records get projects Semester <pk>
i2g-admin records create projects Semester --data '{"year": 2026, "season": 1}'
i2g-admin records update projects Semester <pk> --data @changes.json
i2g-admin records delete projects Semester <pk> --confirm-cascade
i2g-admin logout
```

### Global options

These go **before** the command (as in `aws --output yaml ...`):

- `--output table|json` — output format (`text`/`yaml`/`csv` land in a later release).
- `--query <expr>` — client-side projection (JMESPath; lands in a later release).
- `--profile <name>` — select a named configuration/credentials profile.
- `--version` — print the version and exit.
- `--data` accepts inline JSON, `@file.json`, or `@-` to read JSON from stdin.
- `--json` (per command) is a back-compat alias for `--output json`.

Access requires the logged-in account be active **and** staff. There are no per-model
permission checks — staff status is the gate, backed by the backend's hard denylist.

## Develop

```bash
cd cli && pip install -e ".[test]"
pytest --cov=i2g_admin --cov-report=term-missing
```

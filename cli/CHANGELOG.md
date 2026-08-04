# Changelog

All notable changes to the `i2g-admin` CLI are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `csv-raw` output for explicitly trusted machine consumers.

### Changed

- Default `csv` output neutralizes spreadsheet-formula prefixes.
- The `apps` command filters results through the signed-in account's
  `admin_apps` grants; superusers retain full visibility.
- Typer 0.18.0 and Click 8.3.3 are pinned as the tested callback-compatible
  pair used by the 0.2 command layout.

### Security

- The CLI no longer imports `.env` from its current working directory and only
  accepts its two `I2G_ADMIN_*` keys from the package-owned development file.
- OAuth and API sessions ignore ambient proxy/netrc environment configuration,
  preventing an untrusted working directory or shell proxy from intercepting
  bearer-token traffic.
- Click is upgraded to 8.3.3 to address `PYSEC-2026-2132`; CI also audits with
  patched pip and setuptools releases instead of suppressing toolchain findings.

## [0.2.0] - 2026-06-04

This release reshapes the CLI toward AWS-CLI-style ergonomics: named profiles,
global options, multiple output formats, JMESPath projection, auto-pagination,
HTTP retries, shell completion, skeleton generation, a waiter, and richer
introspection — backed by a refactor into a runtime/commands/formatters layout.

### Added

- **Named profiles** — keep several environments side by side. `config.json` holds
  per-profile settings (`base_url`) and the active `default_profile`; the `default`
  profile reuses the legacy `credentials.json`, while named profiles use
  `credentials-<name>.json` (all `0600`). Select with `--profile <name>` or
  `I2G_ADMIN_PROFILE`. Profile names are restricted to `[A-Za-z0-9._-]`.
- **`configure get/set/list`** — AWS-style configuration subcommands, in addition
  to the back-compat bare `configure` and `configure --base-url <url>`.
- **Global options on the root** (placed *before* the command, AWS-style):
  `--profile`, `--output`, `--query`, `--no-paginate`, `--max-items`, `--page-size`,
  `--max-attempts`, `--connect-timeout`, `--read-timeout`, `--debug`, `--version`.
- **Output formats** — `--output table|json|text|yaml|csv`, with `--json` as a
  per-command alias for `--output json`.
- **`--query`** — client-side JMESPath projection of any result.
- **Auto-pagination** — `records list` walks all pages by default; control it with
  `--no-paginate`, `--max-items <n>`, and `--page-size <n>`.
- **HTTP robustness** — `--max-attempts` retries transient `429/5xx` (and transient
  network errors) with exponential backoff + full jitter, honoring `Retry-After`;
  per-request `--connect-timeout` / `--read-timeout` (defaults 5s / 30s).
- **`apps`** — list the Django apps reachable through the admin API (backed by a new
  `GET /admin-api/apps/`).
- **`records count`** — count matching records without fetching rows (backed by
  `?count=1` on the list endpoint).
- **`records wait <app> <model> --until field=value`** — poll until a record reaches
  the desired state, with `--timeout` / `--interval`.
- **`completion show <shell>`** — print a bash/zsh/fish completion script (alongside
  Typer's built-in `--install-completion` / `--show-completion`).
- **`records create/update --generate-cli-skeleton`** (print an empty JSON template
  from the model schema) and **`--cli-input-json <json|@file>`** (submit it back).
- **Richer `schema`** — fields now include verbose name, help text, default,
  blank/null, choices with labels, and FK target model + pk.
- **`--debug`** — emit the error `repr` on failures.

### Changed

- **No baked-in backend URL.** The base URL resolves from the active profile's
  stored `base_url`, then the legacy `credentials.json`, then `I2G_ADMIN_BASE_URL`
  (env or `cli/.env`). A missing value is a clear configuration error — there is no
  hardcoded production default.
- **Package layout** carved into extension seams: a Typer root in `app.py`, one
  module per command group under `commands/`, shared glue in a leaf `runtime.py`
  (command modules import `runtime`, not `app`, to avoid an import cycle), a
  per-invocation `Context`, and pluggable `--output` / `--query` pipelines.

## [0.1.0]

### Added

- Initial release: OAuth2 Authorization Code + PKCE login that rides the existing
  staff admin login, a cached `0600` bearer token, and generic record CRUD over
  `/admin-api/` (`login`, `logout`, `whoami`, `models`, `schema`,
  `records list/get/create/update/delete`, `configure`).

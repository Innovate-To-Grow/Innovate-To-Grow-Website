# Code Quality Rules

Executable size, complexity, and dependency rules for the active code: the Django backend (`src/`),
the React SPA (`pages/`), the `i2g-admin` CLI (`cli/`), the archive service (`archive/page/`), and the
CI helpers (`scripts/`). Every rule here is enforced by a check you can run locally. CI and the
pre-push hooks run the same commands.

## Commands

| Check | Command | Fails on |
|---|---|---|
| Python size / complexity / nesting / directory size | `python scripts/ci/check_python_quality.py` (`--quiet` for the summary only, `--json out.json` for every finding) | an unexcepted hard finding, or a stale exception |
| Python app dependency directions + import cycles | `python scripts/ci/check_python_dependencies.py` (`--graph` prints app-to-app import counts) | a boundary violation or cycle not listed in `python_dependencies.toml`, or a stale entry |
| TypeScript size / complexity / nesting (hard limits) | `cd pages && npm run lint` | any ESLint error (the hard limits are ESLint errors) |
| TypeScript advisory report | `cd pages && npm run quality:report` (`-- --json out.json`) | never (always exits 0) |
| Frontend layer boundaries, cycles, directory size | `cd pages && npm run check:structure` | a boundary violation, a new cycle, or a directory over the hard limit |
| `core/services` structure (existing, stricter) | `cd src && python manage.py test apps.core.tests.services.test_core_services_structure --settings=config.settings.local` | a file over 200 physical lines, or more than 10 `.py` files in one directory |

Run both Python checks from the repository root with the dev virtualenv active: complexity comes from
`ruff` on `PATH` (the version pinned in `src/requirements/local.txt`). Where they run:

- **CI:** `lint.yml` (Python Linting job) runs both Python checks after Ruff. `ci.yml` (Frontend ESLint
  job) runs `npm run lint` and then `npm run check:structure`. The checkers' own unit tests
  (`scripts/ci/tests/test_check_python_*.py`) run in the Preflight job with the other CI script tests.
- **Pre-push hooks** (`.pre-commit-config.yaml`): `frontend-eslint`, `frontend-structure`, `python-quality`,
  `python-dependencies`.

## Thresholds

Each limit has two levels. Going over the **advisory** level is reported for planned cleanup and
never blocks anything. Going over the **hard** level fails the check unless an individually documented
exception covers it.

| Metric | Advisory (reported when more than) | Hard (fails when more than) |
|---|---|---|
| Ordinary application source file | 300 lines | 500 lines |
| Ordinary business-logic function | 50 lines | 100 lines |
| Function cyclomatic complexity | 10 | 15 |
| Control-flow nesting | 3 levels | 4 levels |
| Source files directly in one directory | 15 | 25 |
| New module dependency cycle | — | any |
| Violation of a declared dependency boundary | — | any |

### Profiles: code that is not ordinary business logic

| Profile | Applies to | Differences from the defaults above |
|---|---|---|
| Python tests | `*/tests/*`, `test_*.py`, `tests.py`, `conftest.py` | File 600 / 1200; no function-length, nesting, or complexity limit (tests are flat arrange/act/assert sequences) |
| Python settings | `src/config/settings/*` | File 400 / 700 (declarative settings and the admin sidebar are long literal tables) |
| TS hooks | `src/**/use*.ts(x)` | Function length 100 / 200 (a hook body holds its callbacks) |
| TS React components | `src/**/*.tsx` | Function length 100 / 200; complexity 15 / 25 (JSX is declarative markup, and every conditional render — `cond && <X/>`, a ternary, `?.` — counts toward complexity) |
| TS tests | `src/__tests__/**`, `*.test.ts(x)`, `e2e/**` | File 600 / 1200; no function-length or complexity limit; nesting 4 / 6 |
| TS config | `pages/*.config.ts` | Ordinary limits |

TypeScript profiles are applied in order and a later match overrides an earlier one, so a `.tsx` file
named `useX.tsx` gets the component limits. In Python the first matching profile wins.

### Never measured

Database migrations, `__pycache__`, virtualenvs, `node_modules`, vendored static libraries
(`src/assets/vendor/`), collectstatic output (`src/static/`, `src/staticfiles/`), media, lockfiles,
build output (`pages/dist/`), and the historical archive material (`archive/legacy/`).
These exclusions name generated, third-party, or historical code only. No application directory is
excluded to hide findings.

## Counting rules

**Python** (`check_python_quality.py`, standard-library `ast` + `tokenize`):

- *Lines* are **code lines**. Blank lines, comment-only lines, and docstring lines are not counted. Every
  physical line of a multi-line statement counts (a 6-line call is 6 lines).
- *Function length* is the code lines from the `def` line to the function's last line. Nested functions
  count toward their enclosing function and are also measured on their own. Methods are named
  `Class.method`.
- *Nesting* is the deepest stack of `if` / `for` / `while` / `try` / `with` / `match` blocks inside a
  function body. An `elif` chain is one level, as are the `except` / `else` / `finally` clauses of one
  `try`. Nested functions, classes, and lambdas start again from zero.
- *Complexity* is Ruff's `C901` (McCabe cyclomatic complexity), the same definition `ruff check
  --select C901` reports.
- *Directory size* is the `.py` files directly in one directory. `__init__.py` is not counted.

**TypeScript** (ESLint core rules, configured in `pages/eslint.quality.js`):

- *Lines* (`max-lines`, `max-lines-per-function`) skip blank and comment-only lines
  (`skipBlankLines`, `skipComments`). A function's length includes its nested callbacks.
- *Complexity* is ESLint's `complexity` rule (classic cyclomatic complexity, which counts `&&`, `||`,
  `??`, `?.` and default parameters as branches). The numbers are therefore not comparable with Python's
  McCabe scores, and the two languages are reported separately.
- *Nesting* is ESLint's `max-depth` (nested blocks inside one function).
- *Directory size* (`check-structure.mjs`) is the `.ts`/`.tsx` files directly in one directory of
  `src/` or `e2e/`, tests included. `index.ts` is not counted.

**The existing `core/services` rule stays, with different semantics.** `test_core_services_structure`
counts **physical** lines (blank and comment lines included) with a 200-line limit, and **all** `.py`
files including `__init__.py` with a 10-file limit, inside `src/apps/core/services/`. It is
deliberately stricter than the repository-wide rules. Both apply there.

### Keeping advisory findings out of `--max-warnings=0`

`npm run lint` runs with `--max-warnings=0`, so any warning blocks. The ESLint config therefore holds
**only the hard limits, as errors**. The advisory thresholds are never in the lint config:
`npm run quality:report` runs ESLint through its Node API with the advisory overrides layered on top
and always exits 0. `pages/eslint.config.js` also sets `reportUnusedDisableDirectives: 'error'`, so an
`eslint-disable` that no longer suppresses anything has to be removed.

## Dependency directions

### Backend apps

Configured in `scripts/ci/python_dependencies.toml` and checked over every module of `src/apps/`
(tests and migrations excluded). Only imports that run at module import time are checked. Imports
inside functions and under `if TYPE_CHECKING:` are not import-time dependencies, so they are excluded
from the cycle check. They still count for boundaries.

| App | May import (besides itself) |
|---|---|
| `core` | nothing (framework app) |
| `authn` | `core` |
| `event` | `core`, `authn` |
| `cms` | `core`, `authn`, `event` |
| `mail` | `core`, `authn`, `cms`, `event`; from `system_intelligence` only `models` and `services.bedrock` |
| `projects` | `core`, `authn`; from `system_intelligence` only `models`, `services.agents`, `services.bedrock`, `services.public_assistant`, `services.usage_log` |
| `system_intelligence` | `core`, `authn`, `cms`, `event`, `mail`, `projects` (its admin assistant reads every app) |
| `cli_admin` | `core` (it reaches models only through `core.services.db_tools.safe_orm`) |

An entry can be a whole app or one public module path inside it. A module entry admits that module and
its submodules only (`event.services.public` does not admit `event.services.public_extra`).

**Composition and registration entry points.** Shared machinery in `core` never imports a business
app. Apps plug in instead:

- **Background jobs:** each app's `AppConfig.ready()` calls
  `apps.core.services.background_jobs.register_job_kind(...)` with dotted handler paths
  (`authn`, `cms`, `event`, `mail`).
- **CSP frame hosts:** `core`'s CSP middleware reads the provider callables listed in the
  `CSP_FRAME_HOST_PROVIDERS` setting (`cms` supplies the embed-host allowlist).
- **Project-level wiring:** `src/config/` (URLs, settings) and the operational management commands in
  `apps.core.management.commands.*` (the background worker and its maintenance list, seeding, and
  service-config checks) are composition roots and may import any app.

**Exceptions** are listed individually in the TOML file as `from` (an fnmatch pattern of the importing
module), `to` (a module prefix), and a `reason`. There are five today, each a lazily imported admin or
ticket helper whose target cannot move without changing a Django app label. **Known import cycles** would
be listed with their member modules and a reason; there are none. (The last two, in `mail.admin.campaign`
and `mail.admin.inbox`, came from views patching services through their own package `__init__`; the
views now import a leaf `services.py` module instead.) An entry that no longer matches anything fails the
check, so the lists only shrink.

### Frontend layers

Checked by `pages/scripts/check-structure.mjs`. Layers, lowest first. A module may import its own
layer and anything lower, never a higher one:

```
types, assets  <  lib  <  hooks, components  <  features  <  routes  <  app (+ main.tsx)
```

- A feature imports another feature **only** through its public entry points:
  `features/<name>/index.ts`, or its data layer `features/<name>/api/**`.
- `routes/` and `app/` are composition layers. They may deep-import feature modules, because a lazy
  route needs the deep import to keep its own chunk (a barrel import would pull every component and
  its CSS into the route chunk).
- Values that a lower layer needs from a higher one are passed in, never imported. For example, the
  CMS embed page receives the router's `EMBED_APP_ROUTES` as a prop.
- Cycles are computed over static value imports (`import type` and dynamic `import()` excluded).
  `KNOWN_CYCLES` is empty, and any new cycle fails.

## Exceptions policy

1. **Fix first.** Split along a real responsibility boundary: a helper per step, a module per concern.
   Do not shuffle lines to get under a number.
2. If a hard finding is genuinely better left as it is, add **one entry for exactly that finding**, with
   a reason saying why splitting would not make the code easier to maintain:
   - Python size, complexity, and nesting: `[[exceptions]]` in `scripts/ci/python_quality.toml`, keyed by
     the key the checker prints (`metric:path::symbol`).
   - Python dependencies: `[[exceptions]]` or `[[cycles]]` in `scripts/ci/python_dependencies.toml`.
   - Frontend directory size: `DIRECTORY_EXCEPTIONS` in `check-structure.mjs`. Frontend cycles:
     `KNOWN_CYCLES`. ESLint hard limits: an `eslint-disable-next-line <rule> -- <reason>` comment on
     that one function.
3. Never exclude a whole application directory to silence findings.
4. Stale exceptions fail the checks, so an entry is removed in the change that fixes the code.

**Current exceptions:**

| Where | Finding | Reason |
|---|---|---|
| `python_dependencies.toml` | 5 boundary exceptions, no cycles | See the `reason` of each entry. |

ESLint has no `eslint-disable` exception for a quality rule. The frontend has no directory exception and
no known cycle.

## Baseline

Measured with the counting rules above at the start of the refactor (base `378dfecd`) and after it.

| Python (advisory / hard) | Before | After |
|---|---|---|
| file-lines | 16 / 6 | 1 / 0 |
| function-lines | 61 / 11 | 1 / 1 |
| nesting | 32 / 7 | 1 / 0 |
| complexity | 33 / 10 | 1 / 0 |
| directory-files | 4 / 2 | 0 / 0 |
| app boundary violations / import cycles | 59 / 5 | 0 / 0 unlisted (5 exceptions, no cycles) |

Every Python finding left in the "After" column is in in-progress status-page work that was untracked
when these checks landed (`scripts/ci/validate_status_infrastructure.py`, `src/apps/core/services/status/`)
and is not part of the committed tree. `python_quality.toml` has no exception for it, so the hard
`function-lines` finding (`validate_observability_and_iam`, 121 lines) must be split, or given an
exception, in the change that commits that work.

| TypeScript (advisory unless noted) | Before | After |
|---|---|---|
| application code, hard findings (ESLint errors) | 41 in 28 files | 0 |
| application code: max-lines / max-lines-per-function / complexity / max-depth | 17 / 52 / 51 / 10 | 0 / 0 / 0 / 0 |
| tests and E2E helpers: max-lines | 11 | 0 |
| layer-boundary violations / import cycles | 17 / 1 | 0 / 0 |

Advisory findings are the planned-cleanup backlog; it is empty apart from the in-progress work above. Print
the current list with `python scripts/ci/check_python_quality.py` and `npm run quality:report`.

### Splitting a long test file

A test file over the limit is split by the behaviour its tests cover, into files named
`<Subject>.<area>.test.tsx` beside it (for example `PastProjectsBuilder.draft.test.tsx`), each with
its own `describe` title. `vi.mock` calls are hoisted per file, so each file declares its own mocks. A
large module stand-in that several files share lives in a plain module next to them and is loaded by
the factory: `vi.mock('@/features/projects', async () => (await import('@/__tests__/…/stub')).stub(…))`.
Fixtures that do not depend on mocks can move to such a module too.

## Related pages

- [Repository Structure](repository-structure.md) — where each responsibility lives
- [Backend](backend.md) · [Frontend](frontend.md)

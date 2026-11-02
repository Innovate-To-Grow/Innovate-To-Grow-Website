# CI/CD

GitHub Actions pipelines for linting, testing, building, and deploying.

Compute-intensive jobs can use the repository's [AWS ephemeral runner fleet](../../aws/ci-runners/README.md).
The fleet scales from zero to 32 machines; `AWS_RUNNERS_ENABLED` controls routing,
and lightweight planning and result jobs stay on GitHub to avoid cold-start delays.
Pull requests from forks never use the fleet: fleet-routed jobs fall back to GitHub-hosted
`ubuntu-24.04` runners, and jobs pinned to `ubuntu-latest` run there as for any pull request.
A `merge_group` run is routed like a push.

## Workflow files

| File | Purpose | Trigger |
|------|---------|---------|
| `.github/workflows/ci.yml` | Full lint, test, build, and security pipeline; reports the required `CI Result` check | Every pull request, merge-queue groups, and pushes to `main`/`master` that touch a CI path |
| `.github/workflows/lint.yml` | Python style, Bandit, and code-structure checks | Reusable workflow, called by `ci.yml` |
| `.github/workflows/codeql.yml` | CodeQL for Python and JavaScript/TypeScript | Push to `main`/`master`, weekly |
| `.github/workflows/dependency-audit.yml` | `npm audit` and `pip-audit` against the live advisory databases | Weekly, manual |
| `.github/workflows/aws-runner-smoke.yml` | Smoke test of the AWS runner fleet | PRs touching `aws/ci-runners/`, manual |
| `.github/workflows/deploy-production.yml` | Unified production approval and deployment orchestration | CI success on `main`, or manual on `main`. **Disabled since 2026-11-01**, see [Deployment pause](#deployment-pause-since-2026-11-01) |
| `.github/workflows/deploy-backend.yml` | Backend deployment to ECS | Reusable workflow call |
| `.github/workflows/deploy-frontend.yml` | Frontend deployment to Amplify | Reusable workflow call |
| `.github/workflows/deploy-archive.yml` | Archive deployment to ECS | Reusable workflow call |

## CI pipeline (`ci.yml`)

### Triggers and scoping

- **`pull_request`** has no path filter, so every pull request reports `CI Result`.
  The `changes` job (`scripts/ci/plan_changed_areas.py`) runs the full suite when
  the diff touches any path in `on.push.paths` or anything else under `.github/`
  (the planner errs toward running). Otherwise it skips every gated job and only
  the ungated checks run: Preflight, `Secrets Scan`, `Frontend npm Audit`, and
  `Python Security Audit`, so a docs-only pull request finishes in a few minutes.
  The two audits compare the lockfiles with live advisory databases, so a newly
  published advisory can still turn such a run red.
- **`merge_group`** is the merge queue's group commit, the tree that lands on
  `main`. It is planned from the group's diff exactly like a pull request.
- **`push`** to `main`/`master` runs only when a CI path changed, and then always
  runs the full suite.

### What runs

| Area | Checks |
|------|--------|
| Preflight | actionlint, YAML/TOML/JSON validity, tool-version pins (`scripts/ci/validate_tool_versions.py`), CI script unit tests (`scripts/ci/tests/`), AWS runner guard tests, legacy viewer infrastructure, Dependabot labels |
| Python style (`lint.yml`) | Ruff lint and format (pinned in `src/requirements/local.txt`), code structure (`scripts/ci/check_python_quality.py`), app import boundaries (`scripts/ci/check_python_dependencies.py`), Bandit with `.bandit-baseline.json` |
| Backend | Migration drift and apply checks on PostgreSQL 16; production settings import and `manage.py check --deploy`; Django tests per app on PostgreSQL with `config.settings.environments.unit` and the per-app floors in `scripts/ci/backend_coverage_floors.json`; `apps.cli_admin` plus `safe_orm` at 100% coverage; Docker build with hadolint, a runtime smoke test, and Trivy (fixable CRITICAL/HIGH) |
| CLI | `cli/` pytest with 99% line and 98% branch coverage floors |
| Frontend | ESLint and `check:structure`, TypeScript, Vitest with the coverage thresholds in `pages/vitest.config.ts`, production build, bundle size, built CSS/HTML checks, the required Chromium smoke test, SBOM and license allowlist |
| End-to-end | All 10 Playwright projects, see below |
| Security | gitleaks on the commit range, Semgrep, `npm audit`, `pip-audit` |
| Archive | `archive/page` pytest |

Backend jobs run Python 3.14, the minor of the production image
(`BACKEND_PYTHON_VERSION`); lint, audit, and CLI jobs run Python 3.11
(`PYTHON_VERSION`). Every job that sets up Node uses 22.22.2 (`NODE_VERSION`); Preflight's
AWS runner guard test (`node --test`) uses the `ubuntu-latest` image's default Node.

Semgrep fails the job on error-severity findings and on a Semgrep failure.
Warnings and notes do not block; push runs upload every finding to the
repository's Security tab, as does the Trivy image scan. Suppress a reviewed
false positive in place with `# nosemgrep: <rule id>` on the line where the
finding starts.

### End-to-end (Playwright)

- Runs all 10 projects declared in `pages/playwright.config.ts` (3 desktop
  engines + 7 mobile/tablet devices), each as its own matrix leg
- Gates `CI Result` through the `E2E Required Result` aggregator, so a failing
  device leg blocks the merge
- Retries a failed test up to twice within its leg (`retries` in
  `pages/playwright.config.ts`, CI only). A pass on retry is reported as flaky
  in the merged report and does not fail the leg; a test that fails all three
  attempts does. The required Chromium smoke runs with `--retries=0` on purpose.
- `E2E Report` (the merged HTML/JUnit report) stays `continue-on-error`: a flaky
  artifact download must not be able to block a merge
- The Playwright container image, the npm package (pinned exactly in
  `pages/package.json`), the e2e venv cache label, and the image the AWS runners
  pre-pull (`aws/ci-runners/bake-image.sh`) move together;
  `validate_tool_versions.py` fails preflight if they drift

### Concurrency

Superseded pull request runs are cancelled. Pushes to `main` are never
cancelled once running, but GitHub keeps at most one *pending* run per group:
when a third push arrives while one run is in progress and one is waiting, the
waiting run is cancelled. Only the newest `main` commit is then guaranteed a
complete push run; with the merge queue, every merged tree has already passed
its `merge_group` run.

## PR / main parity

**A pull request runs the same job set as the push to main that follows it.**
`scripts/ci/plan_changed_areas.py` returns the full suite for any pull request
or merge group touching a path listed in `on.push.paths`;
`scripts/ci/plan_e2e_tests.py` and `scripts/ci/plan_django_tests.py` return the
full device matrix and all eight app suites for every event. A green pull
request check therefore implies a green main run for the same tree.

Only these jobs are push-only, because they publish deploy artifacts and need
repository credentials. While deployments are paused they are also gated off
(see below):

| Job | Pre-merge proxy |
|-----|-----------------|
| `Backend Image Publish` (pushes `itg-backend:<sha>` to ECR) | `Backend Docker Build and Scan` builds the same `context: src` on every pull request |
| `Frontend Production Build Artifact` | `Frontend CI Build Artifact` |

CI used to scope pull request jobs by diff. PR #433 was backend-only, so the
whole E2E matrix was skipped on the PR and ran for the first time after the
merge, where the `iphone14` and `ipad` legs failed (run 32107167026). That run
still reported `CI Result` green and triggered `Deploy Production`, because
`e2e` was `continue-on-error: true` and the old `e2e-informational-result` was
not in `ci-result`'s needs.

Closing that hole took both halves: pull requests now run the same matrix,
**and** a failing leg fails `CI Result` through `E2E Required Result`.
Reverting either half reopens it. Don't reintroduce diff-scoping:
`test_pull_request_and_push_agree_whenever_ci_runs` in
`scripts/ci/tests/test_plan_changed_areas.py` guards the parity half.

## Deployment pause (since 2026-11-01)

`Deploy Production` was disabled manually on 2026-11-01
(`gh workflow list --all` shows `disabled_manually`). Nothing deploys while it
is off, so CI stops producing the deploy artifacts as well: `Backend Image
Publish`, `Frontend Production Build Artifact`, and the image export in
`Backend Docker Build and Scan` run on pushes to `main` only when the
repository variable `DEPLOY_ARTIFACTS_ENABLED` is `true`. `Deploy Artifact
Result` passes when they are skipped.

To resume deployments:

1. Wait until no CI run on `main` is queued or in progress
   (`gh run list --workflow ci.yml --branch main --status in_progress`, and the
   same with `--status queued`), or cancel those runs. A run that started
   during the pause publishes no image even if it finishes after step 3.
2. `gh variable set DEPLOY_ARTIFACTS_ENABLED --body true`
3. `gh workflow enable deploy-production.yml`
4. Merge a change that touches a CI path. Its `main` CI run publishes
   `itg-backend:<sha>` and, on success, starts `Deploy Production`, which waits
   in `Manual Deployment Approval`.

`Deploy Production` only promotes a CI run whose `Backend Image Publish` job
succeeded; for any other run it stops before the approval step. A manual
`Deploy Production` run therefore only works for a `main` commit whose CI run
started with the variable set. Do not use "Re-run failed jobs" on a `main` run
from the pause; merge a new change or use "Re-run all jobs" instead.

## Deploy pipelines

`Deploy Production` is the only production entry point. After a successful
`main` CI run, it requests one approval through the protected
`Manual Deployment Approval` environment and then calls all three component
workflows with the triggering commit SHA. See
[Production Deployment Approval](production.md) for environment setup and the
reviewer migration procedure.

Each component workflow loads its configuration, including secret ARN
references, from its own `itg/<component>/deploy-config` entry in AWS Secrets
Manager through `scripts/deploy/load_config.py`. The deploy workflows read no
GitHub Actions secrets or variables. The one GitHub-side switch on the release
path is CI's repository variable `DEPLOY_ARTIFACTS_ENABLED`: `main` CI publishes
the `itg-backend:<sha>` image that `deploy-backend.yml` pulls only while it is
`true`, so it must stay set whenever `Deploy Production` is enabled.

### Backend (`deploy-backend.yml`)

1. Pull the SHA-tagged Docker image published by the successful CI run
2. Extract and upload Django static assets
3. Render both the Web and no-port background-worker containers from `aws/task-definition.json`
4. Validate shared image/env/secrets, worker entrypoint isolation, health dependency, and the task CPU/memory envelope
5. Run the release migrations in a standalone ECS task; stop on failure, then deploy the two-container task via `aws-actions/amazon-ecs-deploy-task-definition`
6. Run smoke tests:
   - Readiness endpoint check (`/readyz/`)
   - CORS header validation
   - JSON response validation

The backend deploy job uses the `AWS ECS - Prod` GitHub Environment and
updates `itg-backend-service` at `https://api.i2g.ucmerced.edu`.

### Frontend (`deploy-frontend.yml`)

1. Build with `npm run build`
2. Zip the `dist/` output
3. Upload to S3 via AWS pre-signed URL
4. Trigger Amplify deployment

The frontend deploy job uses the `AWS Amplify - Prod` GitHub Environment,
with `https://i2g.ucmerced.edu` as the default frontend URL and
`https://api.i2g.ucmerced.edu` as the default API base.

The frontend builds in the deploy job so `VITE_API_BASE_URL` can come from its
deploy configuration. The backend worker is the sole writer of Amplify custom
rules. The frontend workflow only publishes the build and never replaces the
rule list.

### Archive (`deploy-archive.yml`)

The archive workflow checks out the approved commit, builds and publishes its
container image, deploys the ECS service, and runs HTTPS smoke checks.

All component workflows use environment-specific OIDC role ARNs.
CI publishes the already tested/scanned backend image using its own main-only role.
See [production authentication](production.md#aws-authentication-and-rollout).

## Branch strategy

- **CI** runs on every pull request, on merge-queue groups, and on pushes to
  `main`/`master` that touch a CI path
- **Deployment** triggers only after successful CI completion on `main`, and is
  currently paused
- **Manual deployment** starts only from the unified workflow on `main`
- Component workflows are reusable calls and cannot bypass the unified approval gate

## Monitoring CI

- All workflow runs visible at the repository's Actions tab
- `CI Timing Report` adds a per-job duration table to each run's summary
- Semgrep and Trivy findings from `main` appear in the Security tab
- Deploy smoke tests catch basic runtime issues (readiness, CORS)
- CloudWatch logs capture runtime errors after deployment

## Adding to the pipeline

When adding new CI stages:
1. Add the step to the appropriate workflow file in `.github/workflows/`
2. For new backend checks, use `--settings=config.settings.environments.local` (SQLite) or `--settings=config.settings.environments.test` (PostgreSQL)
3. For new frontend checks, use a Node.js release allowed by `pages/package.json`
4. Keep stages independent where possible for parallel execution
5. Pin new third-party actions to a full commit SHA with a `# vX.Y.Z` comment

## Related pages

- [Backend Deployment](backend.md) — ECS deployment details
- [Frontend Deployment](frontend.md) — Amplify deployment details
- [Environments](environments.md) — CI vs dev vs prod settings
- [Local Development](local-development.md) — Running the same checks locally

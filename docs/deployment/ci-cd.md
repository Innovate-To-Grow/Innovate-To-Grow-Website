# CI/CD

GitHub Actions validates every deployable component, publishes immutable
artifacts from successful `main` runs, and promotes those exact artifacts to
production. The required branch-protection check is `CI Result`.

## Workflows

| File | Purpose | Trigger |
|---|---|---|
| `.github/workflows/ci.yml` | Tests, coverage, security, builds, scans, artifact publication | Push and pull request |
| `.github/workflows/lint.yml` | Reusable Ruff, format, and Bandit gate | Called by CI |
| `.github/workflows/codeql.yml` | CodeQL analysis | Push, pull request, schedule |
| `.github/workflows/deploy-production.yml` | Select CI artifacts and approve the complete production deployment set once | Successful `main` CI |
| `.github/workflows/deploy-backend.yml` | Promote backend image/static assets to ECS/S3 | Reusable call |
| `.github/workflows/deploy-frontend.yml` | Promote target-specific frontend artifact to Amplify | Reusable call |
| `.github/workflows/deploy-archive.yml` | Promote archive image to ECS | Reusable call |
| `.github/workflows/deploy-break-glass.yml` | Audited immutable emergency deploy | Manual, protected environment |

Normal production deploy workflows do not expose `workflow_dispatch`.
`Deploy Production` inspects the successful CI run, shows all selected
components behind one `Production Deployments` approval card, and then invokes
only the reusable workflows whose immutable artifacts exist.

## Change routing

Pull requests run the affected component jobs plus the stable aggregate result.
Every push to `main` runs the complete deployable suite so publication never
depends on an incomplete path filter. CLI-only and archive-only changes have
dedicated required result jobs.

## Backend gate

Backend validation includes:

- Ruff, format, Bandit, Django system checks, and migration drift
- hashed lock-file verification and Python dependency audit
- PostgreSQL migration and concurrency coverage
- partitioned Django tests with coverage enforcement
- production settings, CSP, manifest-static, and service-config checks
- Semgrep
- Dockerfile lint, production image build, Trivy scan, and runtime smoke
- export of the exact scanned image for publication

The Docker image installs only `requirements/production.lock.txt`, is based on
a digest-pinned Python 3.11 image, and contains its generated
`staticfiles.json` plus content-hashed static objects.

## Frontend gate

Frontend validation includes:

- ESLint and TypeScript
- Vitest and coverage
- production and target-specific Vite builds
- initial/chunk bundle budgets
- `npm audit --audit-level=moderate`
- supply-chain reporting
- Playwright local and live/admin projects with self-contained PostgreSQL,
  Django seed data, and Vite services in CI

CI publishes separate `frontend-dist-prod` and `frontend-dist-demo` artifacts.
Deployment does not run another Vite build.

## CLI gate

Changes under `cli/` run:

- Ruff
- the complete CLI test suite and coverage
- Bandit
- pip-audit
- wheel/sdist build
- Semgrep

API discovery and record-operation tests cover the same `admin_apps`
authorization boundary.

## Archive gate

Changes under `archive/` run:

- Ruff, tests, coverage, Bandit, and pip-audit
- dependency lock verification
- Dockerfile lint
- archive image build, Trivy scan, and runtime/semantic smoke tests
- export of the exact scanned image for publication

Archive readiness checks configuration plus a small allowlisted Sheets
request. Upstream failures are never cached as successful readiness.

## Security policy

CodeQL runs on pull requests as well as pushes and schedule. Semgrep and
fixable High/Critical Trivy findings are release-blocking. An exception must be
declared in the validated policy file with an owner, rationale, and expiry; an
untracked suppression is not an acceptable release mechanism. Third-party
Actions are pinned to full commit SHAs.

## Immutable publication and deployment

On a successful `main` run, CI publishes:

- backend and archive images tagged with the full commit SHA
- the exact exported images that were scanned
- production and demo frontend artifacts

Deployment resolves the triggering CI run and SHA, obtains short-lived AWS
credentials through GitHub OIDC, and rejects missing/mismatched artifacts.
ECR repositories should enforce tag immutability.

Backend deployment:

1. Registers an isolated one-off task and runs `migrate_locked`.
2. Verifies the migration exit code.
3. Uploads and verifies manifest-hashed static files from the tested image.
4. Updates the worker independently when `BACKGROUND_WORKER_ENABLED=true`,
   including while web queue production remains disabled.
5. Requires a fresh, target-isolated CloudWatch `WorkerHeartbeat` before
   updating the web service; queue production cannot be enabled without the
   worker rollout flag.
6. Runs readiness, semantic, CORS, SHA/digest, and worker checks.

Frontend/archive deployment waits for the service and checks content type plus
semantic payload markers—not only HTTP 200.

Each production service/environment uses a constant concurrency group and
`cancel-in-progress: false`, so a newer run does not cancel an active rollout.

## Break-glass

**Break-glass Production Deploy** accepts a component, full 40-character SHA,
and mandatory reason. Authorization verifies that the SHA is reachable from
`main` and has a successful push CI run. The `Production Break Glass`
environment must require a human reviewer. It then calls the same reusable
immutable deployment workflow as the normal path.

## Branch protection

Require:

- `CI Result`
- CodeQL
- current review/approval rules
- protected `main`

Configure required reviewers on the shared `Production Deployments` gate and a
separate reviewer group on `Production Break Glass`. Keep required reviewers
off the individual AWS target environments after the shared gate is live; they
continue to scope target-specific variables and secrets. Do not store
long-lived AWS access keys in repository or environment secrets.

## Local workflow checks

```bash
python -m unittest discover -s .github/scripts/tests -p 'test_*.py'
actionlint
```

Run the component checks listed in
[Local Development](local-development.md) before pushing. The canonical
evidence is the GitHub Actions run because it supplies PostgreSQL, browser,
container, scan, and artifact-publication conditions.

## Related pages

- [Backend Deployment](backend.md)
- [Frontend Deployment](frontend.md)
- [Environments](environments.md)
- [Production Handoff Runbook](../operations/handoff-runbook.md)

# CI/CD

GitHub Actions pipelines for linting, testing, building, and deploying.

## Workflow files

| File | Purpose | Trigger |
|------|---------|---------|
| `.github/workflows/lint.yml` | Code style checks | Push and PR |
| `.github/workflows/ci.yml` | Full test and build pipeline | Push and PR |
| `.github/workflows/deploy-production.yml` | Unified production approval and deployment orchestration | CI success on main, or manual on main |
| `.github/workflows/deploy-backend.yml` | Backend deployment to ECS | Reusable workflow call |
| `.github/workflows/deploy-frontend.yml` | Frontend deployment to Amplify | Reusable workflow call |
| `.github/workflows/deploy-archive.yml` | Archive deployment to ECS | Reusable workflow call |
| `.github/workflows/deploy-status.yml` | Independent status site and monitoring stack | Reusable workflow call |

## CI pipeline (`ci.yml`)

Runs on every push and pull request. All stages must pass before deployment workflows trigger.

### Stage 1: Code style (`lint.yml`)

**Backend (Python):**
- Uses Ruff 0.8.0
- `ruff check .` — lint check
- `ruff format --check .` — format check

**Frontend (TypeScript):**
- ESLint
- TypeScript type check (`npx tsc --noEmit`)

### Stage 2: Django build and test

- Python 3.11
- `python manage.py migrate` — verify migrations apply
- `python manage.py test --settings=config.settings.local` — run test suite
- `python manage.py check` — Django system checks

Uses SQLite (dev settings) for fast test execution.

### Stage 3: Docker build test

- Builds the backend Docker image from `src/Dockerfile`
- Exports the image as a build artifact
- Validates the image builds successfully without runtime errors

### Stage 4: PostgreSQL migration test

- Spins up PostgreSQL 16 as a GitHub Actions service container
- Runs `python manage.py migrate --settings=config.settings.test`
- Validates no pending migrations (`python manage.py makemigrations --check`)
- Catches migration issues that don't surface with SQLite

### Stage 5: Frontend tests

- Node.js 22.22.2 (or another release allowed by `pages/package.json`)
- Vitest with 4096 MB Node memory limit
- Runs `npm test`

### Stage 6: Frontend build

- `npm run build` (TypeScript compilation + Vite build)
- Validates the production build succeeds

### Stage 7: End-to-end (Playwright)

- Runs all 10 projects declared in `pages/playwright.config.ts` (3 desktop
  engines + 7 mobile/tablet devices), each as its own matrix leg
- Gates `CI Result` through the `E2E Required Result` aggregator, so a failing
  device leg blocks the merge and stops the deploy chain
- `E2E Report` (the merged HTML/JUnit report) stays `continue-on-error`: a flaky
  artifact download must not be able to block a merge

## PR / main parity

**A pull request runs the same job set as the push to main that follows it.**
`scripts/ci/plan_changed_areas.py` returns the full suite for any PR touching a
path listed in `on.push.paths`; `scripts/ci/plan_e2e_tests.py` and
`scripts/ci/plan_django_tests.py` return the full device matrix and all eight app
suites for every event. A green PR check therefore implies a green main run for
the same tree.

Only two jobs are legitimately push-only, because they publish deploy artifacts
and need repository credentials:

| Job | Pre-merge proxy |
|-----|-----------------|
| `Backend Image Publish` (pushes `itg-backend:<sha>` to ECR) | `Backend Docker Build and Scan` builds the same `context: src` on every PR |
| `Frontend Production Build Artifact` | `Frontend CI Build Artifact`, plus a warn-on-PR / fail-on-push `VITE_API_BASE_URL` presence check |

CI used to scope PR jobs by diff. PR #433 was backend-only, so the whole E2E
matrix was skipped on the PR and ran for the first time after the merge, where
the `iphone14` and `ipad` legs failed (run 32107167026). That run still reported
`CI Result` green and triggered `Deploy Production`, because `e2e` was
`continue-on-error: true` and the old `e2e-informational-result` was not in
`ci-result`'s needs.

Closing that hole took both halves: PRs now run the same matrix, **and** a
failing leg fails `CI Result` through `E2E Required Result`. Reverting either
half reopens it. Don't reintroduce diff-scoping —
`test_pull_request_and_push_agree_whenever_ci_runs` in
`scripts/ci/tests/test_plan_changed_areas.py` guards the parity half.

## Deploy pipelines

`Deploy Production` is the only automatic production entry point. After a
successful `main` CI run, it requests one approval through the protected
`Production Deployments` environment and then calls all three component
workflows with the triggering commit SHA. See
[Production Deployment Approval](production.md) for environment setup and the
reviewer migration procedure.

### Backend (`deploy-backend.yml`)

1. Pull the SHA-tagged Docker image published by the successful CI run
2. Extract and upload Django static assets
3. Render both the Web and no-port background-worker containers from `aws/task-definition.json`
4. Validate shared image/env/secrets, worker entrypoint isolation, health dependency, and the task CPU/memory envelope
5. Deploy the two-container task to ECS via `aws-actions/amazon-ecs-deploy-task-definition@v2`
6. Run smoke tests:
   - Readiness endpoint check (`/readyz/`)
   - CORS header validation
   - JSON response validation

The backend deploy job runs a target matrix:

| Target | GitHub Environment | Default ECS service | Default URL |
|--------|--------------------|---------------------|-------------|
| `prod` | `AWS ECS - Prod` | `itg-backend-service` | `https://api.i2g.ucmerced.edu` |
| `demo` | `AWS ECS(DEMO) - Prod` | `itg-backend-demo-service` | `https://demo.i2g.ucmerced.edu/admin` |

Each target uses the same backend Docker image tag, but reads its own GitHub
Environment variables and secrets for database, storage, CORS, and ECS service
selection. The demo backend also has a direct origin,
`https://demo-api.i2g.ucmerced.edu`, for health checks and Amplify proxy rules.

### Frontend (`deploy-frontend.yml`)

1. Build with `npm run build`
2. Zip the `dist/` output
3. Upload to S3 via AWS pre-signed URL
4. Trigger Amplify deployment

The frontend deploy job also runs a target matrix:

| Target | GitHub Environment | Default URL | Default API base |
|--------|--------------------|-------------|------------------|
| `prod` | `AWS Amplify - Prod` | `https://i2g.ucmerced.edu` | `https://api.i2g.ucmerced.edu` |
| `demo` | `AWS Amplify(DEMO) - Prod` | `https://demo.i2g.ucmerced.edu` | `https://demo.i2g.ucmerced.edu/api` |

Unlike the single production artifact built in CI, each frontend deploy target
builds in the deploy job so `VITE_API_BASE_URL` can come from that target's
GitHub Environment. The backend worker is the sole writer of Amplify custom
rules; for demo it includes `/admin`, `/static`, and `/media` proxies so
`https://demo.i2g.ucmerced.edu/admin` can front a separate backend origin. The
frontend workflow only publishes the build and never replaces the rule list.

### Archive (`deploy-archive.yml`)

The archive workflow checks out the approved commit, builds and publishes its
container image, deploys the ECS service, and runs HTTPS smoke checks.

### Status (`deploy-status.yml`)

The status workflow deploys the Route53-validated CloudFront certificate in
`us-east-1`, then the private S3, CloudFront, API, monitoring, history, logs,
alarms, and dashboard stack in `us-west-2`. Automatic releases promote the
exact successful CI artifact. Hashed assets are uploaded before `index.html`;
if any post-publish validation fails, the versioned prior index is restored and
CloudFront is invalidated. Public schema/cache, DNS/TLS, private S3, unsigned
internal denial, and signed internal access are all smoke-tested with bounded
polling. See [Status site deployment](status.md) for required environment
variables and recovery details.

All component workflows use credentials and target-specific configuration from
their existing GitHub Environments.

## Branch strategy

- **CI** runs on all pushes and PRs to any branch
- **Deployment** triggers only after successful CI completion on `main`
- **Manual deployment** starts only from the unified workflow on `main`
- Component workflows are reusable calls and cannot bypass the unified approval gate

## Monitoring CI

- All workflow runs visible at the repository's Actions tab
- Deploy smoke tests catch basic runtime issues (readiness, CORS)
- CloudWatch logs capture runtime errors after deployment

## Adding to the pipeline

When adding new CI stages:
1. Add the step to the appropriate workflow file in `.github/workflows/`
2. For new backend checks, use `--settings=config.settings.local` (SQLite) or `--settings=config.settings.test` (PostgreSQL)
3. For new frontend checks, use a Node.js release allowed by `pages/package.json`
4. Keep stages independent where possible for parallel execution

## Related pages

- [Backend Deployment](backend.md) — ECS deployment details
- [Frontend Deployment](frontend.md) — Amplify deployment details
- [Environments](environments.md) — CI vs dev vs prod settings
- [Local Development](local-development.md) — Running the same checks locally

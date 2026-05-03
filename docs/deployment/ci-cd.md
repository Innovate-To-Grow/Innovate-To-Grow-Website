# CI/CD

GitHub Actions pipelines for linting, testing, building, and deploying.

## Workflow files

| File | Purpose | Trigger |
|------|---------|---------|
| `.github/workflows/lint.yml` | Code style checks | Push and PR |
| `.github/workflows/ci.yml` | Full test and build pipeline | Push and PR |
| `.github/workflows/deploy-backend.yml` | Backend deployment to ECS | CI success on main, or manual |
| `.github/workflows/deploy-frontend.yml` | Frontend deployment to Amplify | CI success on main, or manual |

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
- `python manage.py test --settings=core.settings.dev` — run test suite
- `python manage.py check` — Django system checks

Uses SQLite (dev settings) for fast test execution.

### Stage 3: Docker build test

- Builds the backend Docker image from `src/Dockerfile`
- Exports the image as a build artifact
- Validates the image builds successfully without runtime errors

### Stage 4: PostgreSQL migration test

- Spins up PostgreSQL 16 as a GitHub Actions service container
- Runs `python manage.py migrate --settings=core.settings.ci`
- Validates no pending migrations (`python manage.py makemigrations --check`)
- Catches migration issues that don't surface with SQLite

### Stage 5: Frontend tests

- Node.js 20
- Vitest with 4096 MB Node memory limit
- Runs `npm test`

### Stage 6: Frontend build

- `npm run build` (TypeScript compilation + Vite build)
- Validates the production build succeeds

## Deploy pipelines

### Backend (`deploy-backend.yml`)

1. Build Docker image
2. Push to AWS ECR
3. Render ECS task definition from `aws/task-definition.json` template
4. Deploy to ECS via `aws-actions/amazon-ecs-deploy-task-definition@v2`
5. Run smoke tests:
   - Readiness endpoint check (`/readyz/`)
   - CORS header validation
   - JSON response validation

### Frontend (`deploy-frontend.yml`)

1. Build with `npm run build`
2. Zip the `dist/` output
3. Upload to S3 via AWS pre-signed URL
4. Trigger Amplify deployment

Both deploy workflows use AWS credentials stored in GitHub Secrets.

## Branch strategy

- **CI** runs on all pushes and PRs to any branch
- **Deployment** triggers only on successful CI completion on `main`
- Both deploy workflows support manual dispatch for ad-hoc deployments

## Monitoring CI

- All workflow runs visible at the repository's Actions tab
- Deploy smoke tests catch basic runtime issues (readiness, CORS)
- CloudWatch logs capture runtime errors after deployment

## Adding to the pipeline

When adding new CI stages:
1. Add the step to the appropriate workflow file in `.github/workflows/`
2. For new backend checks, use `--settings=core.settings.dev` (SQLite) or `--settings=core.settings.ci` (PostgreSQL)
3. For new frontend checks, ensure Node.js 20 compatibility
4. Keep stages independent where possible for parallel execution

## Related pages

- [Backend Deployment](backend.md) — ECS deployment details
- [Frontend Deployment](frontend.md) — Amplify deployment details
- [Environments](environments.md) — CI vs dev vs prod settings
- [Local Development](local-development.md) — Running the same checks locally

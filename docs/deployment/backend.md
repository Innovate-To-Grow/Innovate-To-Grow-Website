# Backend Deployment

The backend runs as a Docker container on AWS ECS Fargate, fronted by an Application Load Balancer.

## Docker image

**Dockerfile:** `src/Dockerfile`

- Base image: Python 3.11 slim, pinned by digest
- System dependencies: `libpq-dev` (PostgreSQL client library)
- Python dependencies: production-only, installed with hashes from
  `src/requirements/production.lock.txt`
- Exposed port: 8000
- Default process: Uvicorn; the entrypoint starts only the requested process

```
uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers 2 --limit-concurrency 20
```

### Build

```bash
cd src
docker build -t itg-backend .
```

CI builds, scans, and exports the image once. Deployment loads and pushes that
exact image under the full triggering SHA; it does not rebuild it.

## ECS task definition

**Template:** `aws/task-definition.json`

| Setting | Value |
|---------|-------|
| Task family | `itg-backend` |
| Network mode | `awsvpc` (Fargate) |
| CPU | 512 (0.5 vCPU) |
| Memory | 1024 MB |
| Container port | 8000 |
| Log driver | `awslogs` → CloudWatch `/ecs/itg-backend` (us-west-2) |

## ECS service scaling

The production ECS service is `itg-backend-service` in cluster `itg-backend-cluster`.

| Setting | Value |
|---------|-------|
| Desired count | 1 |
| Auto Scaling minimum | 1 |
| Auto Scaling maximum | 10 |

This scaling target is currently managed in AWS Application Auto Scaling rather than a repo-tracked IaC template.

### Container health check

```
python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/livez/')"
```

- Interval: 30 seconds
- Timeout: 5 seconds
- Retries: 3
- Start period: 60 seconds
- Uses `/livez/` so database connection saturation does not trigger ECS task churn.

### Environment injection

The deploy workflow (`deploy-backend.yml`) renders task definitions from
environment-scoped GitHub variables and secret ARNs. GitHub obtains
short-lived AWS credentials through OIDC; no long-lived AWS access-key secrets
are required. See [the production deployment configuration](production.md).

## Deployment flow

Called by the `deploy-production.yml` workflow after its unified approval (or
by the separately approved break-glass workflow):

1. **Select**: Resolve the successful `main` CI run and immutable full SHA
2. **Promote**: Use the exact CI-scanned image, published under that SHA
3. **Migrate**: Register an isolated task and run `migrate_locked --noinput`
   under a PostgreSQL advisory lock
4. **Static assets**: Upload the manifest-hashed assets baked into that tested
   image and verify `staticfiles.json`; retain old hashes through rollback
5. **Worker**: When `BACKGROUND_WORKER_ENABLED=true`, update the worker first
   while the web producer may remain disabled
6. **Heartbeat gate**: Verify the exact worker task revision stayed active and
   wait for a fresh CloudWatch `WorkerHeartbeat` in the target-specific
   namespace
7. **Web**: Update the web task only after the worker gate passes; the workflow
   rejects `BACKGROUND_JOBS_ENABLED=true` unless the worker rollout flag is
   also true
8. **Smoke tests**: Automated checks after deploy:
   - Readiness endpoint responds at `/readyz/`
   - CORS headers present
   - Semantic JSON response validates
   - Worker heartbeat is fresh whenever the worker is deployed

Backend CSP defaults to report-only. After the seven-day review described in
the [handoff runbook](../operations/handoff-runbook.md), set the protected
environment variable `CSP_REPORT_ONLY=false` and deploy through this same
immutable workflow; the rendered web task definition persists enforcement
across subsequent rollouts and rollbacks.

For the initial durable-job rollout, deploy once with
`BACKGROUND_WORKER_ENABLED=true` and `BACKGROUND_JOBS_ENABLED=false`. After
that deployment proves the worker heartbeat, deploy again with both flags true
to enable web queue production. If `BACKGROUND_WORKER_ENABLED` is not defined,
it inherits the legacy `BACKGROUND_JOBS_ENABLED` value; both default off.

### Trigger conditions

- Automatically selected by `Deploy Production` after successful CI completion
  on `main`
- Normal production workflows have no manual trigger
- Emergency rollback/redeploy uses the separately protected break-glass
  workflow with a main-reachable full SHA and mandatory reason

## Uvicorn configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Workers | 2 by default (`WEB_CONCURRENCY`) | Keep PostgreSQL connection pressure below the `db.t4g.micro` ceiling |
| Concurrency cap | 20 by default (`UVICORN_LIMIT_CONCURRENCY`) | Provide backpressure before the app exhausts DB connections |
| Graceful shutdown | 120s | Accommodate long-running operations (sheet sync, email campaigns) |
| Bind | `0.0.0.0:8000` | Listen on all interfaces (required for Fargate networking) |

## Health endpoints

`HealthCheckMiddleware` intercepts these paths before URL routing:

| Path | Purpose | Database check |
|------|---------|----------------|
| `/livez/` | Docker/ECS/ALB liveness probe | No |
| `/readyz/` | Deploy smoke test and monitoring readiness probe | Yes |
| `/health/` | Frontend-compatible health and maintenance payload | Yes |

`/readyz/` and `/health/` return HTTP 503 when database connectivity fails. `/health/` keeps the existing JSON fields used by the frontend:

```json
{"status": "ok", "database": "ok", "maintenance": false, "maintenance_message": ""}
```

## Production settings

`config.settings.production` applies security hardening:

- `DEBUG = False`
- `SECURE_HSTS_SECONDS` enabled
- `SECURE_SSL_REDIRECT = True` (via proxy header)
- `SESSION_COOKIE_SECURE = True`
- `CSRF_COOKIE_SECURE = True`
- `SECURE_SERVER_HEADER = None` (strip server identification)
- Structured JSON logging to CloudWatch

## Database

PostgreSQL with SSL required. Connection parameters are injected via environment variables. Persistent Django connections default to off in production (`DB_CONN_MAX_AGE=0`) to keep the `db.t4g.micro` connection count below its ceiling.

## Static and media files

Served from S3 via `django-storages`:

| Path | Source |
|------|--------|
| `/static/` | Collected static files (admin CSS, CKEditor assets) |
| `/media/` | User uploads (CMS assets, profile images) |

`collectstatic` runs once while building the tested image using
`config.settings.build`. Normal web/worker startup performs no migration,
collection, or account bootstrap. Deployment uploads the baked hashed assets
without `--size-only` and never deletes prior hashes during rollout.

## Related pages

- [Frontend Deployment](frontend.md) — Amplify deployment
- [CI/CD](ci-cd.md) — Build and deploy pipelines
- [Environments](environments.md) — Environment variable reference
- [Architecture: Backend](../architecture/backend.md) — App and middleware structure
- [Production Handoff Runbook](../operations/handoff-runbook.md) — Operations and rollback

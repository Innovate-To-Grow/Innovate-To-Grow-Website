# Backend Deployment

The backend runs as a Docker container on AWS ECS Fargate, fronted by an Application Load Balancer.

## Docker image

**Dockerfile:** `src/Dockerfile`

- Base image: `python:3.11-slim`
- System dependencies: `libpq-dev` (PostgreSQL client library)
- Python dependencies: installed from `src/requirements.txt`
- Exposed port: 8000
- Entry command: Uvicorn

```
uvicorn core.asgi:application --host 0.0.0.0 --port 8000 --workers 2 --limit-concurrency 20
```

### Build

```bash
cd src
docker build -t itg-backend .
```

The CI pipeline builds and validates the Docker image on every push.

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

The deploy workflow (`deploy-backend.yml`) substitutes GitHub Secrets into the task definition template using a Python script. All environment variables listed in [Environments](environments.md) are injected at deploy time.

## Deployment flow

Triggered by the `deploy-backend.yml` GitHub Actions workflow:

1. **Build**: Docker image built from `src/Dockerfile`
2. **Push**: Image pushed to AWS ECR
3. **Task definition**: Template rendered with environment variables from GitHub Secrets
4. **Deploy**: ECS task definition updated via `aws-actions/amazon-ecs-deploy-task-definition@v2`
5. **Smoke tests**: Automated checks after deploy:
   - Readiness endpoint responds at `/readyz/`
   - CORS headers present
   - JSON response validates

### Trigger conditions

- Automatically on successful CI completion (main branch)
- Manually via workflow dispatch

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

`core.settings.prod` applies security hardening:

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

`collectstatic` is typically run during container startup or as a deploy step.

## Related pages

- [Frontend Deployment](frontend.md) — Amplify deployment
- [CI/CD](ci-cd.md) — Build and deploy pipelines
- [Environments](environments.md) — Environment variable reference
- [Architecture: Backend](../architecture/backend.md) — App and middleware structure

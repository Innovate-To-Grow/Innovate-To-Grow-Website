# Backend Deployment

The backend runs as a Docker container on AWS ECS Fargate, fronted by an Application Load Balancer.

## Docker image

**Dockerfile:** `src/Dockerfile`

- Base image: `python:3.11-slim`
- System dependencies: `libpq-dev` (PostgreSQL client library)
- Python dependencies: installed from `src/requirements.txt`
- Exposed port: 8000
- Entry command: Gunicorn

```
gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 4 --threads 2 --timeout 120
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
python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')"
```

- Interval: 30 seconds
- Timeout: 5 seconds
- Retries: 3
- Start period: 60 seconds

### Environment injection

The deploy workflow (`deploy-backend.yml`) substitutes GitHub Secrets into the task definition template using a Python script. All environment variables listed in [Environments](environments.md) are injected at deploy time.

## Deployment flow

Triggered by the `deploy-backend.yml` GitHub Actions workflow:

1. **Build**: Docker image built from `src/Dockerfile`
2. **Push**: Image pushed to AWS ECR
3. **Task definition**: Template rendered with environment variables from GitHub Secrets
4. **Deploy**: ECS task definition updated via `aws-actions/amazon-ecs-deploy-task-definition@v2`
5. **Smoke tests**: Automated checks after deploy:
   - Health endpoint responds at `/health/`
   - CORS headers present
   - JSON response validates

### Trigger conditions

- Automatically on successful CI completion (main branch)
- Manually via workflow dispatch

## Gunicorn configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Workers | 4 | 2× vCPU count (Fargate 0.5 vCPU, rounded up) |
| Threads | 2 | Handle concurrent requests within each worker |
| Timeout | 120s | Accommodate long-running operations (sheet sync, email campaigns) |
| Bind | `0.0.0.0:8000` | Listen on all interfaces (required for Fargate networking) |

## Health check endpoint

`GET /health/` is intercepted by `HealthCheckMiddleware` before URL routing:

```json
{"status": "ok", "database": true, "maintenance": false}
```

Always returns HTTP 200 to keep ALB probes passing. The `database` and `maintenance` fields reflect actual state for monitoring.

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

PostgreSQL with SSL required. Connection parameters injected via environment variables. Django ORM handles connection pooling at the default level; Gunicorn workers each maintain their own connections.

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

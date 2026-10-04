# Backend Deployment

The backend runs as one AWS ECS Fargate task with a Web container and a durable
background-worker sidecar. Only the Web container is registered with the
Application Load Balancer.

## Docker image

**Dockerfile:** `src/Dockerfile`

- Base image: `python:3.11-slim`
- System dependencies: `libpq-dev` (PostgreSQL client library)
- Python dependencies: installed from `src/requirements.txt`
- Exposed port: 8000
- Entry command: Uvicorn

```
uvicorn config.deploy.asgi:application --host 0.0.0.0 --port 8000 --workers 2 --limit-concurrency 20
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
| CPU | 1024 (1 vCPU) |
| Memory | 2048 MB |
| Web | `itg-backend`: 768 CPU units, 1024 MB reservation, port 8000 |
| Worker | `itg-background-worker`: 256 CPU units, 512 MB reservation, no port |
| Log driver | `awslogs` → CloudWatch `/ecs/itg-backend` (`ecs` and `worker` stream prefixes) |

Both containers use the same SHA-pinned image, environment, Secrets Manager or
SSM references, task role, database, and cache configuration. Without
`REDIS_URL` (production today) each container has its own file cache; see
[Environments: production cache](environments.md#production-cache-today). The
worker explicitly replaces the image entrypoint with:

```text
python manage.py run_background_worker --settings=config.settings.production
```

It therefore does not run startup migrations, create the demo administrator,
collect static files, or start Uvicorn. Its ECS `HEALTHY` dependency on
`itg-backend` delays the worker until the Web entrypoint has completed
migrations and the liveness check passes. The worker is essential: an
unexpected worker exit replaces the whole task instead of leaving a healthy
Web process with an unconsumed queue. SIGTERM receives the Fargate maximum
120-second stop window. Besides jobs, the worker runs the hourly database
maintenance (retired RSA keys, public-assistant budgets, send-verification rows,
expired sessions, login failure windows) listed in
[Send verification: scheduled cleanup](send-verification.md#scheduled-cleanup).

The task was increased from 0.5 vCPU/1 GiB to 1 vCPU/2 GiB so the second Django
runtime cannot starve Web requests or trigger avoidable out-of-memory restarts.
The tradeoff is the higher Fargate task price. ECS service scaling creates one
worker per Web task; row-level queue claiming makes that concurrency safe, but
operators should include worker/database load when raising the Web maximum.

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

The deploy workflow (`deploy-backend.yml`) substitutes GitHub Secrets into the task definition template using a Python script. All environment variables listed in [Environments](environments.md) are injected at deploy time. It stamps both Web and worker with `AMPLIFY_CONFIG_REVISION=<github.run_id>.<github.run_attempt>`, giving every deployment attempt a shared, monotonically comparable Amplify configuration generation.

## Deployment flow

Triggered by the `deploy-backend.yml` GitHub Actions workflow:

1. **Build**: Docker image built from `src/Dockerfile`
2. **Push**: Image pushed to AWS ECR
3. **Task definition**: Template rendered with environment variables and secret ARNs; the same values are copied to the worker
4. **Validation**: Deployment fails if the worker can run the Web entrypoint, exposes a port, loses shared configuration, or exceeds the task resource envelope
5. **Deploy**: ECS task definition updated via `aws-actions/amazon-ecs-deploy-task-definition@v2`
6. **Smoke tests**: Automated checks after deploy:
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

## Client IP and proxy trust

Every per-IP throttle (login, email/phone verification codes, send-verification challenges, CLI OAuth, …) and the
app's own `client_ip()` helper need the *real* client address. Production traffic is
`browser → ALB → ECS task (uvicorn)`. Uvicorn is started without `--forwarded-allow-ips`, so it trusts only
`127.0.0.1` and never rewrites the peer address: Django sees `REMOTE_ADDR` = the ALB's private VPC address and the
raw `X-Forwarded-For` header. The ALB **appends** the address it received the connection from, so every entry to
the left of the last one is client-supplied and forgeable.

`NUM_PROXIES` says how many trailing `X-Forwarded-For` entries belong to our own proxies; the Nth entry from the
right is the client.

| | |
|---|---|
| Env var | `NUM_PROXIES` (integer ≥ 1, default `1`; startup fails on anything else). Not a secret. |
| Where it is applied | `settings.NUM_PROXIES` (used by `apps.core.utils.client_ip`) **and** `REST_FRAMEWORK["NUM_PROXIES"]` (used by DRF's throttle `get_ident()`, which ignores the top-level setting). Both are set once in `config/settings/production.py`. |
| Deployment | `aws/task-definition.json` carries `__NUM_PROXIES__`; `deploy-backend.yml` renders it from the `NUM_PROXIES` GitHub Environment variable (default `1`) and `aws/validate_backend_task_definition.py` rejects a rendered value that is not a positive integer. |
| Local / CI | Unset (no proxy): DRF falls back to the full header / `REMOTE_ADDR`. |

ALB requirements (both are the AWS defaults; do not change them): `routing.http.xff_header_processing.mode = append`
(with `preserve` the last entry would be client-controlled) and `routing.http.xff_client_port.enabled = false`
(otherwise entries become `ip:port` and each connection would get a fresh throttle bucket).

**Extra hops.** Setting the value too low is safe but coarse (throttles key on the outermost trusted proxy's
address); too high trusts a client-controlled entry and re-opens the bypass. The demo frontend calls the API through
the Amplify domain (`VITE_API_BASE_URL=https://demo.i2g.ucmerced.edu/api`, proxied by the Amplify rewrite to the
ALB), so requests there pass through CloudFront *and* the ALB. It is deployed with `NUM_PROXIES=1` (throttles then
key on the edge address). Only raise its `NUM_PROXIES` GitHub Environment variable to `2` after confirming from a
real request that CloudFront appended the viewer address to `X-Forwarded-For`. Production's frontend calls
`https://api.i2g.ucmerced.edu` directly, which is one hop. The archive service is a Flask app without DRF throttling
and is not affected.

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
- Plain-text console logging (`LEVEL time module pid tid message`) to CloudWatch Logs

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

# Production Deployment Configuration

Production deploys are artifact promotions. A successful `CI` run on `main`
publishes backend/archive images under the full commit SHA and uploads separate
`frontend-dist-prod` and `frontend-dist-demo` artifacts. `Deploy Production`
selects the components that produced artifacts, requests one approval for the
complete deployment set, and then calls the component workflows. They consume
the exact CI artifacts; they do not rebuild source or publish `latest` tags. A
component that was unchanged in the triggering CI run skips its deploy cleanly.

Normal deployment workflows have no manual trigger. Emergency rollback or
redeploy uses **Break-glass Production Deploy**, which accepts a component, a
full 40-character SHA, and an incident/change reason. It rejects commits that
are not on `main` and commits without a successful push CI run.

## GitHub environments

Create and protect these environments:

- `Production Deployments`
- `AWS ECS - Prod`
- `AWS ECS(DEMO) - Prod`
- `AWS Amplify - Prod`
- `AWS Amplify(DEMO) - Prod`
- `AWS ECS - Archive Prod`
- `Production Break Glass`

Configure required reviewers on `Production Deployments` and
`Production Break Glass`. Keep the two reviewer lists independent so emergency
access is deliberate and auditable. The five AWS target environments retain
their target-specific variables, secrets, and deployment history but must not
also require reviewers; otherwise GitHub requests a second approval after the
unified gate.

Migrate protection in this order: create and protect `Production Deployments`,
merge the workflow change, verify that its approval job waits, and only then
remove required reviewers from the five AWS target environments. Never remove
the target protection before the unified gate exists on `main`.

Environment-specific variables take precedence over repository variables.
Use the prod and demo environments for values that differ between targets.

## AWS identity

Set `AWS_GITHUB_ACTIONS_ROLE_ARN` to the complete IAM role ARN used by GitHub
Actions, and set `AWS_REGION` if the deployment region is not `us-west-2`.
The workflows obtain short-lived AWS credentials through GitHub OIDC; do not
configure long-lived `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` secrets.

The IAM role trust policy must restrict the repository and the production
environments above. Its permissions must cover only the repositories,
clusters, services, task definitions, Amplify apps, log groups, secret
references, and static buckets listed below. It also needs `iam:PassRole` for
the configured ECS execution and task roles. The backend deploy role needs
`cloudwatch:GetMetricStatistics` for the worker rollout gate, and the ECS task
role needs `cloudwatch:PutMetricData` for its environment-specific background
job metrics namespace.

Configure the `itg-backend` and `itg-archive` ECR repositories with tag
immutability. CI exports the image that passed Trivy, transfers that exact
Docker image between jobs, and only loads, SHA-tags, and pushes it; the publish
jobs never rebuild source.

## Backend ECS variables

Required for both backend environments:

- `DJANGO_SECRET_KEY_SECRET_ARN`
- `DB_NAME`, `DB_USER`, `DB_HOST`
- `DB_PASSWORD_SECRET_ARN`
- `ECS_EXECUTION_ROLE_ARN`, `ECS_TASK_ROLE_ARN`

The values ending in `_SECRET_ARN` are complete AWS Secrets Manager or SSM
Parameter Store ARNs, never literal secret material.

Defaults exist for the current cluster/service names, URLs, task families, log
groups, region, and storage buckets. Set these variables when the AWS resources
differ:

- `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`
- `ECS_TASK_FAMILY`, `ECS_LOG_GROUP`
- `FRONTEND_URL`, `BACKEND_URL`, `VITE_API_BASE_URL`
- `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`
- `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
  `CORS_ALLOWED_ORIGINS`
- `CSP_REPORT_ONLY` (`true` by default; set `false` only after the documented
  seven-day report review)
- `DB_ENGINE`, `DB_PORT`, `DB_CONN_MAX_AGE`,
  `DB_CONN_HEALTH_CHECKS`
- `REDIS_URL_SECRET_ARN`
- `WEB_CONCURRENCY`, `UVICORN_LIMIT_CONCURRENCY`

The deploy registers an isolated one-off task definition, runs
`migrate_locked --noinput`, and requires a zero exit code before updating the
web service. The demo environment can then run the create-only
`ensure_default_admin` command. Configure its email and password reference
with:

- `ENSURE_DEFAULT_ADMIN` (`true` by default only for demo)
- `DJANGO_SUPERUSER_EMAIL`
- `DJANGO_SUPERUSER_PASSWORD_SECRET_ARN`
- optionally `DJANGO_SUPERUSER_USERNAME`,
  `DJANGO_SUPERUSER_FIRST_NAME`, and `DJANGO_SUPERUSER_LAST_NAME`

An existing administrator is never modified or reset by the deploy.

### Background worker

Worker deployment and web queue production are separate controls so the schema
and consumer can be proven healthy before any web process creates jobs. Both
controls default off. Set these for the worker-first rollout:

- `BACKGROUND_WORKER_ENABLED=true`
- `BACKGROUND_JOBS_ENABLED=false`
- `REDIS_URL_SECRET_ARN`
- `ECS_WORKER_SERVICE`
- `ECS_WORKER_TASK_FAMILY`
- `ECS_WORKER_LOG_GROUP`
- optionally `BACKGROUND_JOB_METRICS_NAMESPACE` (defaults to distinct
  `I2G/BackgroundJobs/Prod` and `I2G/BackgroundJobs/Demo` namespaces)
- optionally `BACKGROUND_WORKER_HEARTBEAT_MAX_AGE_SECONDS` (default `180`)
- optionally `BACKGROUND_WORKER_HEARTBEAT_TIMEOUT_SECONDS` (default `300`)

The ECS worker service must already exist with a Fargate network configuration.
After migration, deployment updates it to the immutable backend image, sets
its desired count to one, verifies that ECS retained that exact task
definition, and polls CloudWatch for a fresh `WorkerHeartbeat`. The web task is
not updated until the heartbeat gate passes. Its task definition receives the
same validated
`DJANGO_ALLOWED_HOSTS`, `BACKEND_URL`, `AWS_STORAGE_BUCKET_NAME`, and
`AWS_S3_REGION_NAME` values as the web and one-off tasks, because importing the
production settings requires them even though the worker does not serve HTTP.

Keep metric namespaces unique per environment; otherwise one environment could
not prove which worker produced a heartbeat. After the worker-first deployment
is green, change only `BACKGROUND_JOBS_ENABLED=true` and deploy again while
leaving `BACKGROUND_WORKER_ENABLED=true`. The workflow refuses to deploy a web
producer when the worker flag is false. For compatibility, an environment that
has not defined `BACKGROUND_WORKER_ENABLED` inherits its existing
`BACKGROUND_JOBS_ENABLED` value, while an environment with neither flag stays
off.

To shut down, first deploy with `BACKGROUND_JOBS_ENABLED=false` and
`BACKGROUND_WORKER_ENABLED=true`, drain or reconcile the remaining jobs, then
scale the worker service to zero and set `BACKGROUND_WORKER_ENABLED=false`. A
disabled worker deployment deliberately does not mutate an existing ECS
service.

Static files are copied from the tested image only after migration succeeds.
The Django production settings must use manifest-hashed static filenames so
new and old web revisions can overlap safely during rollout.

## Frontend Amplify variables

Required for both frontend environments:

- `AMPLIFY_APP_ID`
- `VITE_API_BASE_URL`
- `AMPLIFY_CSP_FRAME_SOURCES`: comma- or whitespace-separated HTTPS origins
  currently permitted by the CMS Embed Allowed Hosts configuration (for
  example, `https://*.youtube.com https://archive.i2g.ucmerced.edu`)

Optional overrides:

- `AMPLIFY_BRANCH` (default `main`)
- `FRONTEND_URL`
- `AMPLIFY_BACKEND_PROXY_URL`
- `AMPLIFY_PROXY_ADMIN_PATHS`
- `AMPLIFY_CSP_MODE`

`AMPLIFY_CSP_MODE` defaults to `report-only`. After CSP reports show that the
policy is complete, set it to `enforce` in the target environment. The policy
permits scripts only from the application origin, `cdn.userway.org`, and
`siteimproveanalytics.com`; it never grants `unsafe-inline` or `unsafe-eval`
for scripts. Both modes send violations to the backend `/csp-report/` endpoint.
Update `AMPLIFY_CSP_FRAME_SOURCES` whenever an operator changes the CMS iframe
host allowlist; deployment rejects empty, non-HTTPS, path-bearing, or malformed
entries.

## Archive ECS variables

The archive environment requires:

- `SHEETS_API_KEY_SECRET_ARN`
- `ECS_EXECUTION_ROLE_ARN`
- `ECS_TASK_ROLE_ARN`

The Sheets credential variable must contain a complete Secrets Manager or SSM
ARN. The deployed service must allow the documented archive smoke-test range;
the workflow checks liveness, readiness, the embed page, and a real Sheets
proxy response after every rollout.

## Repository protection

Keep Dependabot enabled for the root frontend, backend Python, standalone CLI,
archive Python, GitHub Actions, and both Docker build contexts. Require the
aggregate `CI Result` check on `main`, and leave CodeQL enabled for pushes,
pull requests, and its scheduled scan.

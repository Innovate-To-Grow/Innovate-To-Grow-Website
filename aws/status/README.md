# I2G status infrastructure

This directory contains the independently hosted status service for
`status.i2g.ucmerced.edu`.

## Regional layout

- Deploy `certificate-template.yaml` in `us-east-1`. It creates only the ACM
  certificate required by CloudFront and validates it through Route53.
- Deploy `template.yaml` in `us-west-2`. It owns the status S3 bucket,
  CloudFront distribution, Route53 records, API Gateway, Lambda functions,
  DynamoDB table, five-minute Scheduler, DLQ, dashboard, logs, and actionless
  alarms.
- The public API is served through the same origin at `/api/status`. The direct
  `/prod/internal/status` API Gateway route requires AWS IAM signing and is
  granted only to the configured backend ECS task role.

## Required deployment parameters

The deployment workflow must provide these values explicitly:

- `CertificateArn`
- `HostedZoneId`
- `BackendTaskRoleName`
- `ProductionTargetGroupArn`, `DemoTargetGroupArn`, `ArchiveTargetGroupArn`
- `ProductionAmplifyAppId`, `DemoAmplifyAppId`
- `ReleaseSha` (the exact approved commit)

Existing ECS service, RDS, asset bucket, branch, and domain names have safe
repository defaults matching production. They remain parameters so the stack
can be validated in an isolated account without editing the template.

## Data and state behavior

- Scheduler supplies `<aws.scheduler.scheduled-time>` explicitly. That time,
  not Lambda wall-clock time, is the five-minute idempotency slot.
- Component sample, daily rollup, current state, and incident changes share one
  DynamoDB transaction. Current/system snapshots only accept newer scheduled
  slots.
- Public and staff snapshots use separate `PUBLIC` and `INTERNAL` partition
  keys. The public reader's IAM policy cannot read the internal partition; the
  internal reader can read only that partition.
- Two consecutive failures open an incident; two consecutive successes resolve
  it. Unknown samples break either streak without opening or resolving an
  incident. Explicit maintenance opens immediately and is excluded from uptime.
- Raw samples expire after 8 days, daily history and resolved incidents after
  100 days, and run claims after 2 days. Active incident metadata has no TTL;
  its retention starts when it resolves.
- Current hashed assets are never age-expired. CI/CD tags only safely retired
  `assets/` objects with `status-retire=true`; the lifecycle rule removes those
  objects after 30 days. The deploy workflow must keep the current and rollback
  release assets untagged.

## Local validation

```sh
python -m pip install -r aws/status/requirements-dev.txt
PYTHONPATH=aws/status/functions pytest -q aws/status/tests
ruff check aws/status/functions aws/status/tests
ruff format --check aws/status/functions aws/status/tests
cfn-lint aws/status/certificate-template.yaml aws/status/template.yaml
sam build --template-file aws/status/template.yaml
sam validate --lint --region us-west-2 --template-file aws/status/template.yaml
```

Tests mock every network and AWS interaction. Local/PR validation does not call
the production endpoints and does not create AWS resources.

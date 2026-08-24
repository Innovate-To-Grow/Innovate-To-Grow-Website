# Status site deployment

The public service-status site is an independent static application at
`https://status.i2g.ucmerced.edu`. Its application, data plane, probes, and
origin resources run in `us-west-2`. A small CloudFormation stack in
`us-east-1` owns only the ACM certificate required by CloudFront.

## Release flow

Status releases use the repository's unified production workflow:

1. A successful `CI` run on `main` starts `Deploy Production`.
2. The existing `Production Deployments` environment supplies the single
   human approval for every production target.
3. `deploy-status.yml` checks out the approved commit, deploys the certificate
   stack, then deploys the main SAM stack in `us-west-2`.
4. The workflow uploads immutable assets before `index.html`, invokes the probe
   once, waits for CloudFront, and runs public and IAM-authenticated smoke tests.
5. The backend deployment receives the status stack's public and internal URLs
   so the staff-only Django dashboard can use the same release.

The `AWS Status - Prod` GitHub Environment records the status deployment and
holds status-specific variables. It must not have a second required reviewer;
the unified approval is the release boundary.

Before the first release, create that environment and remove required-reviewer
rules from the existing per-target Amplify, ECS, and Archive environments.
Those environments still scope their own variables, secrets, and deployment
URLs, but `Production Deployments` must be the only reviewer-protected gate.

Automatic releases promote the `status-dist-production` artifact produced by
the exact successful CI run and verify that run's `head_sha` before upload. A
manual unified deployment is allowed only for the current `main` SHA after that
same SHA has a successful `main` push CI run; it promotes the verified CI status
artifact and backend image rather than bypassing or rebuilding around CI.
If the one-time probe is idempotently rejected because that five-minute slot
already completed, the signed smoke check waits for the next scheduled snapshot
to report the approved release SHA. The bounded poll allows up to seven minutes
so a check that begins just after a scheduler boundary still includes the next
probe's execution time.

## Required GitHub configuration

The status environment reuses the existing `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` secrets for v1. Configure these non-secret variables:

| Variable | Purpose |
| --- | --- |
| `STATUS_DOMAIN_NAME` | Public hostname; defaults to `status.i2g.ucmerced.edu`. |
| `STATUS_HOSTED_ZONE_ID` | Route53 hosted-zone ID used for certificate validation and aliases. |
| `STATUS_BACKEND_TASK_ROLE_NAME` | Existing ECS task role that may invoke only the internal status route. |
| `STATUS_PROD_AMPLIFY_APP_ID` | Production frontend application to inspect. |
| `STATUS_DEMO_AMPLIFY_APP_ID` | Demo frontend application to inspect. |
| `STATUS_PRODUCTION_TARGET_GROUP_ARN` | Production API ALB target group in `us-west-2`. |
| `STATUS_DEMO_TARGET_GROUP_ARN` | Demo API ALB target group in `us-west-2`. |
| `STATUS_ARCHIVE_TARGET_GROUP_ARN` | Archive ALB target group in `us-west-2`. |

Existing ECS, RDS, bucket, and Amplify branch names have repository defaults in
the SAM template. Override them with `STATUS_ECS_CLUSTER_NAME`,
`STATUS_PRODUCTION_ECS_SERVICE`, `STATUS_DEMO_ECS_SERVICE`,
`STATUS_ARCHIVE_ECS_SERVICE`, `STATUS_RDS_INSTANCE_ID`,
`STATUS_PRODUCTION_ASSETS_BUCKET`, `STATUS_DEMO_ASSETS_BUCKET`,
`STATUS_PRODUCTION_AMPLIFY_BRANCH`, and `STATUS_DEMO_AMPLIFY_BRANCH` only when
the environment differs. Stack names may likewise be overridden with
`STATUS_CERTIFICATE_STACK` and `STATUS_STACK`.

The deployment identity needs CloudFormation/SAM, S3 asset upload, CloudFront
invalidation, Lambda invoke, Route53/ACM, and narrowly scoped IAM policy
attachment permissions for the two status stacks. Pull-request jobs never load
these credentials. The deployment identity also needs the same exact internal
`execute-api:Invoke` permission used by the signed post-deploy smoke check, plus
object-tagging access on the status bucket for best-effort asset retirement.
If the AWS credentials currently exist only as environment secrets on another
deployment target, copy the same secret references into `AWS Status - Prod`;
GitHub does not expose one environment's secrets to another environment.

## Runtime behavior

The scheduler probes the five public components every five minutes. DynamoDB
stores raw samples for eight days and daily aggregates/events long enough to
serve a rolling 90-day view. Maintenance and unknown samples are excluded from
the availability denominator. Service outages remain HTTP 200 responses from
the status API and are represented by the response status fields; a missing or
failed status data plane returns a sanitized HTTP 503.

The public site requests only same-origin `/api/status`. The staff dashboard
calls the separate `/prod/internal/status` API using the ECS task role and
SigV4. The public projection never contains AWS resource identifiers, probe
URLs, response bodies, or raw provider errors.

## Rollback and recovery

- CloudFormation and SAM roll back failed infrastructure updates.
- The site bucket is versioned. Deployment records the prior `index.html`
  version and restores it when post-deploy smoke checks fail.
- Hashed assets are uploaded without deleting the previous release, so a
  restored index continues to resolve its assets.
- Only after smoke checks pass, assets absent from both the current build and
  the prior rollback index are tagged `status-retire=true`. The bucket lifecycle
  removes those tagged assets after 30 days; untagged current/rollback assets
  never receive a blanket age-based expiration. A newly retired object is
  self-copied once before tagging so its lifecycle age starts at retirement,
  rather than at the asset's original upload date.
- The DynamoDB table uses retain policies and point-in-time recovery; rolling
  back code does not erase history.
- A fresh installation starts with no historical backfill. The first probe
  initializes the current snapshot and earlier daily bars remain unknown.

The deployment workflow intentionally does not cancel an in-progress status
release. If the unified production concurrency group is occupied by an older
approval, resolve that run before expecting a newer release to start.

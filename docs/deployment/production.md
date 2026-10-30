# Production Deployment Approval

A successful `CI` run on `main` starts the `Deploy Production` workflow. An
operator can also start that workflow manually on `main` to redeploy its
current commit. Both paths pause once on the protected `Manual Deployment Approval`
environment. Approving that single gate releases the complete deployment set:

- backend production on ECS;
- frontend production on Amplify;
- archive production on ECS.

The backend first runs a standalone ECS migration task using the release image
and service network configuration. A nonzero migration exit prevents rollout.
Web containers do not migrate at boot. Database migrations must remain backward
compatible with the currently running release; an ECS rollback never reverses DDL.
An existing migration task prevents another run after a cancelled deployment.
The frontend ships only after the backend has become healthy. Archive deploys
in parallel and has an independent ECS circuit breaker.

Automatic and manual runs promote the same CI-tested backend image, resolved
by its immutable SHA tag to a digest. The CI publish job uploads the tested and
scanned image instead of rebuilding it. Repeated releases reuse existing tags.
Component workflows cannot be manually dispatched.

## GitHub environments

The workflow uses these environments:

- `Manual Deployment Approval` — the single approval gate;
- `AWS ECS - Prod` — backend identity and deployment history;
- `AWS Amplify - Prod` — frontend identity and deployment history;
- `AWS ECS - Archive Prod` — archive identity and deployment history.

Configure required reviewers on `Manual Deployment Approval`. The three target
environments retain their URLs and deployment history. Configuration lives in
AWS Secrets Manager. They must not also require reviewers after the
shared gate is verified. Otherwise GitHub will request a second round of
approvals when the component jobs begin.

Migrate protection in this order:

1. Create `Manual Deployment Approval` and configure its required reviewers.
2. Merge the unified workflow and confirm its approval job waits correctly.
3. Approve the first unified run and complete any existing target approvals.
4. Remove only the required-reviewer rules from the three target environments.
   Keep their URLs and other protection settings intact.
5. Re-run a deployment and verify that only the shared approval is requested.

Never remove the target reviewer rules before the shared gate is present on
`main`. Manual runs are restricted to `main` and reuse its successfully published CI image.

## AWS authentication and rollout

See [the scoped identity stack](../../aws/cicd/identity-stack.json). CI uses
a public role ARN declared in its workflow. Each deployment workflow declares
its own role ARN; no workflow uses a long-lived AWS key. CI trusts only the
repository's main branch. Deployment roles trust their specific GitHub environment,
which must be restricted to the main branch. Keep workflow edits subject to review.
The shared approval still gates all production jobs. Do not enable prevention of
self-review with only one reviewer; designate an independent reviewer first.

Deploy the identity stack before merging the OIDC workflow change. Create the AWS deployment configuration objects
and restrict environment deployment branches to main. Archive needs its dedicated
execution and task role ARNs. Keep the old keys until an OIDC CI publish and all
three deployments succeed; then remove the GitHub keys and retire the IAM access
key after checking other repositories that may share that user.

ECR commit tags must be immutable. The publisher reuses an existing SHA, never
updates `latest`, and deploys the digest. Trivy HIGH/CRITICAL findings with fixes
block CI. Enable ECR push scanning for both image repositories as a second signal.
The backend task role may update rules only for the I2G Amplify app; the archive
task role has no application AWS permissions. Execution-role permissions belong
to the ECS agent and include only the archive image, logs, and Sheets secret.

### AWS-owned deployment configuration

Production settings are stored as JSON objects in Secrets Manager:
`itg/backend/deploy-config`, `itg/frontend/deploy-config`, and
`itg/archive/deploy-config`. Each deployment role can read only its own object.
The loader validates setting names against `aws/cicd/deploy-config-keys.json`
and rejects multiline values before exporting them to the job. Application
passwords and signing keys remain separate secrets injected directly by ECS.

Deployment requires no GitHub Actions secrets or variables. CI runner selection may retain the non-secret `AWS_RUNNERS_ENABLED` bootstrap switch. Public OIDC role ARNs
and the AWS region are bootstrap identifiers in workflow code; they cannot be
fetched before authentication. CI's public API URL is a checked-in test/build
default, while production frontend deployment reads its URL from AWS.

Unused former repository settings are preserved in the backend configuration
for recovery; storing them does not enable new application features. Legacy SES
credentials are backed up separately in `itg/shared/legacy-ses-credentials` and
are not automatically injected into runtime or exposed to deployment roles.

### Application AWS credentials and background jobs

Application credentials are separate from deployment identities. Each AWS
credential configuration references `itg/backend/aws-credentials/<config-id>`.
The secret JSON contains `access_key_id` and `secret_access_key`; the database
retains only its ARN, region, and service metadata. SES, SMS, Bedrock, usage
metrics, and admin test actions use the same resolver. The ECS task role has
read-only access to this namespace. Values are cached only in process memory
for up to 60 seconds before rotation is picked up. Production refuses legacy
database keys and prevents new plaintext writes. The legacy columns remain
empty for a safe staged schema transition and local-test compatibility.

For an initial migration, use a temporary operations role scoped to creating
and reading this secret namespace. Apply schema migrations, then run
`python manage.py migrate_aws_credentials` from the new image before rolling
out the service. This copies and verifies every existing configuration while
keeping legacy values for the old containers. After every service container
runs the new image, run `python manage.py migrate_aws_credentials --clear-legacy`.
The clear phase refuses to erase a database key if its cloud copy differs.
Remove the temporary migration role after verification. Do not roll back to an
image that predates the Secrets Manager resolver after clearing legacy columns.

Set `BACKGROUND_JOBS_ENABLED` to `true` in `itg/backend/deploy-config` to enable
durable queues and startup reconciliation of Amplify rules. The worker waits
for Web readiness. Before initial enablement, inspect pending/retry jobs, then
verify worker heartbeat, successful reconciliation, frontend/API routes, and
provider access. Validate email/SMS with read-only API calls unless an actual
test recipient has been explicitly requested.

# Production Deployment Approval

A successful `CI` run on `main` starts the `Deploy Production` workflow. An
operator can also start that workflow manually on `main` to redeploy its
current commit, provided that exact commit has a successful main CI image. Both
paths enter the `Manual Deployment Approval` environment. This job pauses only
when an enabled, plan-supported required-reviewer rule applies; the environment
name alone does not enforce approval. Once that job completes, the workflow
releases the complete deployment set:

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

- `Manual Deployment Approval` — the shared gate when reviewer protection is enforced;
- `AWS ECS - Prod` — backend identity and deployment history;
- `AWS Amplify - Prod` — frontend identity and deployment history;
- `AWS ECS - Archive Prod` — archive identity and deployment history.

Configure required reviewers on `Manual Deployment Approval` and verify that
the current repository visibility and GitHub plan support them. A green approval
job is not evidence that a human reviewed the release. The three target
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
read-only access to this namespace; the only secret it may write is the
[Microsoft Graph certificate key](#microsoft-graph-certificate-key), which lives
outside it. Values are cached only in process memory
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

### Microsoft Graph certificate key

The Microsoft Graph email provider signs with a private key that a superuser
installs in Django admin. The key is stored in one Secrets Manager secret,
`itg/backend/microsoft-graph/certificate-key`, outside the
`itg/backend/aws-credentials/` namespace. Each install adds a version; the
database keeps only the certificate's public data, the secret ARN and the pinned
version ID. Runbook: [Microsoft Graph email](../integrations/microsoft-graph-email.md#where-the-private-key-is-kept).

This secret is a deliberate exception to the task role's read-only access to
application credentials, and it needs InfoSec sign-off before go-live. The
identity stack defines it as `GraphCertificateKeySecret`,
`ApplicationGraphCertificateKey` and `GraphCertificateKeySecretPolicy`:

- `ecsTaskRole` may call `GetSecretValue`, `DescribeSecret`, `PutSecretValue`
  and `UpdateSecretVersionStage` on that exact secret, and nothing else on it.
- The same policy explicitly denies deleting, restoring, updating, rotating or
  replicating the secret, changing its resource policy, and tagging it.
- The resource policy, with `BlockPublicPolicy`, denies reading the value and
  writing versions to every principal except `ecsTaskRole`. No person can read
  the key through IAM. Break-glass means an account administrator changes the
  resource policy, which CloudTrail records.

Rollout order:

1. Deploy the identity stack before anyone installs a certificate. The secret is
   created empty and retained when the stack is deleted or replaced; never set
   its value by hand. Until it exists, an install fails with an AWS error code
   and changes nothing.
2. Confirm with the account owner that `ecsTaskRole` has no IAM path. The
   resource policy compares `aws:PrincipalArn` with
   `arn:aws:iam::394167325273:role/ecsTaskRole`, the ARN the backend deployer
   passes to ECS.
3. No deploy-config or task-definition change is needed. The production
   settings select the Secrets Manager store (`CREDENTIAL_STORE_BACKEND`) and
   require it (`CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER`). With any other store,
   the `core.E002` system check stops every management command, including
   container start-up. `GRAPH_REQUIRE_ACCESS_EVIDENCE` is on, so email can switch
   to Microsoft Graph only after a recorded, passing access check.
4. Review CloudTrail for the secret after each install and during an incident.
   Expect reads from `ecsTaskRole` sessions about hourly per process and writes
   only when a certificate is installed. Event history keeps 90 days of
   management events; this repository defines no trail.

Image rollback: code from before the Graph provider does not know the `graph`
provider value. Switch email to AWS SES before deploying such an image.
Reversing core migration `0034_microsoft_graph_provider` makes that switch
itself.

### GitHub feature prerequisites

Required reviewers on private repositories depend on the GitHub plan. Free, Pro,
and Team plans offer this protection only for public repositories; check the
[current environment requirements](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
before relying on a release pause. Verify an actual pending review in a test
release, including after repository visibility or plan changes.

CodeQL result uploads for private repositories also require GitHub Code Security
to be enabled. An Advanced Security/Code Security feature error is an account or
repository configuration issue, not a failed application test. Resolve the
[feature prerequisite](https://docs.github.com/en/code-security/reference/code-scanning/troubleshoot-analysis-errors/private-repository-enablement)
before claiming code-scanning uploads work.

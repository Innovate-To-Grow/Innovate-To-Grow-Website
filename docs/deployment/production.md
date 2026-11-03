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

Deployment requires no GitHub Actions secrets. Two non-secret repository variables remain: `AWS_RUNNERS_ENABLED` selects CI runners, and `DEPLOY_ARTIFACTS_ENABLED` must be `true` whenever `Deploy Production` is enabled, because CI publishes the backend release image only while it is set (see [CI/CD: Pausing and resuming deployments](ci-cd.md#pausing-and-resuming-deployments)). Public OIDC role ARNs
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
read-only access to this namespace; the only secrets it may write are the
[Microsoft Graph certificate key](#microsoft-graph-certificate-key) and the
[Gmail API service-account key](#gmail-api-service-account-key), which live
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

The Microsoft Graph email provider signs with a private key that an admin with the
Core app installs in Django admin. The key is stored in one Secrets Manager secret,
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

### Gmail API service-account key

The Gmail API email provider signs with a Google service-account key that an
admin with the Core app installs in Django admin. It is stored in its own Secrets Manager
secret, `itg/backend/gmail-api/service-account-key`, with exactly the same
controls as the Graph key: `GmailApiKeySecret` (created empty, `Retain` on
deletion and replacement), `ApplicationGmailApiKey` (the task role may read,
describe, add versions and relabel, and is denied every lifecycle and policy
action) and `GmailApiKeySecretPolicy` (only `ecsTaskRole` may read the value or
write versions). The database keeps only the store reference, the pinned
version and the key's public facts. The key reaches further than the Graph one:
with domain-wide delegation it can send as any user in the Workspace domain, so
it needs InfoSec sign-off before go-live. Deploy the identity stack before the
first install; until the secret exists an install fails and changes nothing.
Runbook: [Gmail API email](../integrations/gmail-api-email.md).

Image rollback: code from before the Gmail API provider does not know the
`gmail` provider value. Switch email to AWS SES before deploying such an image.

### Delivery rates release

The delivery-rate limiter ([Delivery rates](../integrations/delivery-rates.md))
paces every email, SMS and inbox session. Before or with the release:

1. **IAM reads for Smart rate.** Grant the shared application IAM user (the
   secret behind `AWSCredentialConfig.credentials_secret_arn`, not `ecsTaskRole`)
   `ses:GetAccount`, `sms-voice:DescribeSenderIds` and
   `sms-voice:DescribeSpendLimits` (it already needs
   `sms-voice:DescribePhoneNumbers`). That policy is outside this repository.
   Until `ses:GetAccount` is granted, Smart SES runs on the limit migration
   `core.0036` copied from the old campaign send rate. That copy is flagged as
   carried over: the first limit AWS reports for the account replaces it, with
   no manual step. `sms-voice:DescribePhoneNumbers` being already granted is
   the repository's assumption, not verified **[CONFIRM LIVE]**.
2. **SMTP speed.** If email is sent through SMTP, Smart rate bounds it by the
   60 messages/min fallback (campaigns start at about 22 a minute), far below
   the old campaign send rate (default 600 a minute), which is carried over
   only as the SMTP manual rate. Enter the server's real limit as the SMTP
   **Provider rate limit**, or turn Smart rate off for SMTP, if that matters.
3. **Background worker.** Set `BACKGROUND_JOBS_ENABLED` to `true` (above).
   Without it there is no deferral, priority or lane gating: campaigns are sent
   by a web process and pause on a long hold, and old usage buckets are never
   purged.
4. **Deploy outside campaign sends.** Until every task runs the new image, old
   tasks pace with the `DeliveryRateLimit` table and new ones with the new
   limiter, independently, so their combined rate can double.
5. **Migrations.** `core.0036_delivery_rate_control` (policy, state and usage
   tables, seeded from settings and the active email and Graph configs;
   `BackgroundJob.priority` and its claim index), `core.0037_retire_old_send_rates`
   (hides `MicrosoftGraphProviderConfig.messages_per_minute` and
   `max_send_rate`, keeping both columns), `core.0038_gmail_api_provider` and
   `mail.0020_paused_delivery_status`. None drops or renames a column, so the
   running release (PR #643 alone included) keeps working while they apply.
6. **Image rollback.** ECS rollback never reverses DDL. An image from before
   this release finds every column it reads; switch email off the Gmail API
   before deploying it (it does not know that provider).
   `max_send_rate`, `messages_per_minute` and `DeliveryRateLimit` stay for one
   release so this works; a follow-up release drops them.

### GitHub feature prerequisites

The repository is public, so environment required reviewers, rulesets, the merge
queue, and code-scanning uploads (CodeQL, Semgrep, Trivy) are all available on the
organization's Free plan. If the repository becomes private again, environment
required reviewers and the merge queue need GitHub Enterprise Cloud (Free, Pro and
Team plans offer them only on public repositories), rulesets need Team or higher,
and code-scanning uploads need GitHub Code Security; check the
[current environment requirements](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
and the [code-scanning prerequisite](https://docs.github.com/en/code-security/reference/code-scanning/troubleshoot-analysis-errors/private-repository-enablement).
After any visibility or plan change, verify an actual pending review in a test release.

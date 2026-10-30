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
- `AWS ECS - Prod` — backend configuration;
- `AWS Amplify - Prod` — frontend configuration;
- `AWS ECS - Archive Prod` — archive configuration.

Configure required reviewers on `Manual Deployment Approval`. The three target
environments continue to hold their target-specific variables, secrets, URLs,
and deployment history, but they must not also require reviewers after the
shared gate is verified. Otherwise GitHub will request a second round of
approvals when the component jobs begin.

Migrate protection in this order:

1. Create `Manual Deployment Approval` and configure its required reviewers.
2. Merge the unified workflow and confirm its approval job waits correctly.
3. Approve the first unified run and complete any existing target approvals.
4. Remove only the required-reviewer rules from the three target environments.
   Keep their variables, secrets, URLs, and other protection settings intact.
5. Re-run a deployment and verify that only the shared approval is requested.

Never remove the target reviewer rules before the shared gate is present on
`main`. Manual runs are restricted to `main` and reuse its successfully published CI image.

## AWS authentication and rollout

See [the scoped identity stack](../../aws/cicd/identity-stack.json). CI uses
`AWS_CI_ROLE_ARN` at repository scope. Each production environment has its own
`AWS_DEPLOY_ROLE_ARN`; no workflow uses a long-lived AWS key. CI trusts only the
repository's main branch. Deployment roles trust their specific GitHub environment,
which must be restricted to the main branch. Keep workflow edits subject to review.
The shared approval still gates all production jobs. Do not enable prevention of
self-review with only one reviewer; designate an independent reviewer first.

Deploy the identity stack before merging the OIDC workflow change. Set the role
ARN variables, copy target-specific repository variables into their environments,
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

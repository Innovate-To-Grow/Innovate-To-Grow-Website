# Production Deployment Approval

A successful `CI` run on `main` starts the `Deploy Production` workflow. An
operator can also start that workflow manually on `main` to redeploy its
current commit. Both paths pause once on the protected `Production Deployments`
environment. Approving that single gate releases the complete deployment set:

- backend production and demo on ECS;
- frontend production and demo on Amplify;
- archive production on ECS.

The component workflows are reusable workflows called only by
`deploy-production.yml`. They receive the selected full commit SHA, so automatic
runs promote the backend image published by CI while frontend and archive check
out that exact revision. A manual unified run rebuilds and publishes the backend
image first. Direct manual dispatch of an individual component is intentionally
disabled because it would bypass the shared gate.

## GitHub environments

The workflow uses these environments:

- `Production Deployments` — the single approval gate;
- `AWS ECS - Prod` and `AWS ECS(DEMO) - Prod` — backend configuration;
- `AWS Amplify - Prod` and `AWS Amplify(DEMO) - Prod` — frontend configuration;
- `AWS ECS - Archive Prod` — archive configuration.

Configure required reviewers on `Production Deployments`. The five target
environments continue to hold their target-specific variables, secrets, URLs,
and deployment history, but they must not also require reviewers after the
shared gate is verified. Otherwise GitHub will request a second round of
approvals when the component jobs begin.

Migrate protection in this order:

1. Create `Production Deployments` and configure its required reviewers.
2. Merge the unified workflow and confirm its approval job waits correctly.
3. Approve the first unified run and complete any existing target approvals.
4. Remove only the required-reviewer rules from the five target environments.
   Keep their variables, secrets, URLs, and other protection settings intact.
5. Re-run a deployment and verify that only the shared approval is requested.

Never remove the target reviewer rules before the shared gate is present on
`main`. Manual runs are restricted to `main` and rebuild the backend image for
the selected commit before deployment.

# AWS ephemeral GitHub Actions runners

This repository has a dedicated EC2 runner fleet in account `394167325273`,
region `us-west-2`. It accepts at most **32 concurrent runners**, with **zero
idle runners**. Each machine has 8 vCPUs and 16 GiB RAM and executes one job.
Finishing a job terminates the machine and its encrypted 80 GiB root volume.
An independent 90-minute shutdown deadline covers abandoned or broken runners.

The fleet uses on-demand `c7i.2xlarge` instances, with `c7a.2xlarge` as a capacity
alternative, in three availability zones. The on-demand price checked during
setup was $0.357 per instance-hour for `c7i.2xlarge`; 32 busy instances would
therefore cost $11.424 per hour in EC2 compute. Charges accrue only while the
instances exist. EBS, temporary public IPv4 addresses, image snapshots, logs,
and the serverless control plane are additional usage charges.

## How jobs reach AWS

1. The private **I2G AWS CI Runners** GitHub App receives `workflow_job` events.
   It is installed only on `Innovate-To-Grow/Innovate-To-Grow-Website`.
2. A signed-webhook guard checks the repository, exact runner labels, and the
   workflow run's authoritative GitHub metadata. Fork runs, completed runs,
   mismatched commits, and `pull_request_target` runs cannot launch machines.
3. The pinned `github-aws-runners/github-runner/aws` module (`8.0.0`) queues
   accepted jobs and scales the repository-level runner fleet to its limit.
   Its scale-up function is serialized so launches share one capacity check.
4. Runners fetch their one-use JIT registration configuration from SSM,
   register with GitHub, execute their job, and terminate.
5. A separate encrypted recovery queue checks each accepted job after three
   minutes. If it is still queued, its authoritative repository, commit, labels,
   and status are revalidated before redelivery, at most three times. Started,
   canceled, completed, or untrusted jobs cannot start replacement machines.
   This covers interrupted cold boots and failed queue handoffs without an
   always-on controller. The serialized launch consumer batches up to 32 jobs;
   its three-minute visibility window gives throttled deliveries time to retry.

Heavy CI jobs, CodeQL, dependency audits, and production deployment jobs use
the fleet when repository variable `AWS_RUNNERS_ENABLED` is `true`. Small
planning, approval, lint, and aggregation jobs remain on GitHub-hosted runners
to avoid adding an EC2 cold start to every dependency edge. Fork PRs use the
GitHub-hosted fallback, and the webhook guard independently enforces that
boundary even if a fork edits its workflow. Existing production approval and
OIDC policies remain in effect.

Django unit coverage jobs select `config.settings.environments.unit`, using
the fast password hasher recommended by Django for isolated tests. Default
hashers remain available for existing fixtures. Browser E2E and production
checks use their regular settings, and all test selection and coverage gates
remain in place. See [Django test performance guidance](https://docs.djangoproject.com/en/6.0/topics/testing/overview/#password-hashing).

The required label set is `[self-hosted, Linux, X64, i2g-aws]`. Runners are
temporary: an empty GitHub Runners settings page while no jobs are running is
expected. A newly queued job can take around 1–3 minutes to acquire a cold
machine; this is an expectation, not a startup-time guarantee. Different
workflow stages may each encounter startup latency.

## Network and credentials

The fleet has its own VPC (`10.60.0.0/16`), no peering to production, no inbound
security-group rules, and HTTP/HTTPS-only runner egress for package repositories
and service APIs. Public addresses exist
only for the lifetime of each runner; no NAT gateway or always-on controller
is provisioned. SSM supports administrator troubleshooting without SSH.

App credentials live in encrypted SSM parameters:

- `/i2g-ci/github-app/id`
- `/i2g-ci/github-app/key-base64`
- `/i2g-ci/github-app/webhook-secret`

Terraform stores only parameter references, not private-key values. Its state
is in the private, encrypted, versioned bucket
`i2g-ci-terraform-394167325273-us-west-2`. Use short-lived administrator SSO
credentials to change this infrastructure; never reuse a personal GitHub
OAuth token as a runner-controller credential.

## Runner images

EC2 Image Builder bakes Ubuntu 24.04 with Docker, Node 22.22.2, Python 3.11.18
and 3.14.10, the GitHub runner agent, PostgreSQL 16, and the workflow's pinned
Playwright container. Component validation checks tool installation before
publishing the image. The pipeline runs weekly to refresh the agent and OS
packages, then updates `/imagebuilder/i2g-ci/runner-ami`. Image-builder
instances also terminate when their work is done. A recipe-scoped lifecycle
policy retains three image generations and cleans up older AMIs and snapshots.

Changing workflow tool or container versions requires updating `bake-image.sh`
and its validation in `image.tf`, bumping the component and recipe semantic
versions in `image.tf`, then rebuilding the image. These immutable resources
use create-before-destroy so the existing pipeline can switch safely. Cached virtualenv
keys distinguish GitHub-hosted and self-hosted filesystem layouts.

## Operations

With `AWS_PROFILE` set to an authorized SSO profile:

```bash
python3 aws/ci-runners/prepare-artifacts.py
terraform -chdir=aws/ci-runners init
terraform -chdir=aws/ci-runners plan -out=reviewed.tfplan
terraform -chdir=aws/ci-runners apply reviewed.tfplan
terraform -chdir=aws/ci-runners output runner_pool
```

`prepare-artifacts.py` verifies pinned release digests and builds the guard
archive. Provider versions are locked in `.terraform.lock.hcl`. App creation
for a fresh installation uses `bootstrap-app.py`, followed by installation on
this repository only. Creating another app is not part of routine deployment.

To build an image immediately:

```bash
aws imagebuilder start-image-pipeline-execution --region us-west-2 \
  --image-pipeline-arn arn:aws:imagebuilder:us-west-2:394167325273:image-pipeline/i2g-ci-runner-image
```

Run **AWS Runner Smoke** from GitHub Actions to verify 4, 16, or 32 simultaneous
machines, including cached tools and an isolated PostgreSQL service. It holds
each runner for two minutes so concurrent capacity can be observed, then lets
the machines terminate. Verify EC2 returns to zero pending/running instances
in the CI VPC after the run.

To route new workflow runs back to GitHub immediately, set
`AWS_RUNNERS_ENABLED=false`. Already-queued self-hosted jobs need cancellation
and rerunning to pick up the fallback. The fleet's scheduled scale-down and
runner shutdown deadline still clean up its machines.

Useful logs are `/aws/lambda/i2g-ci-webhook-guard`,
`/aws/lambda/i2g-ci-scale-up`, `/aws/lambda/i2g-ci-scale-down`, and the runner
log groups under `/github-self-hosted-runners/i2g-ci`. Logs must never contain
app keys, installation tokens, JIT configuration, or raw webhook bodies.

## Validation

```bash
node --test aws/ci-runners/guard/trust.test.mjs
actionlint
terraform -chdir=aws/ci-runners fmt -check
terraform -chdir=aws/ci-runners validate
python -m unittest discover -s scripts/ci/tests
```

References: [upstream runner module](https://github.com/github-aws-runners/terraform-aws-github-runner/tree/v8.0.0),
[AWS ephemeral runner guidance](https://aws.amazon.com/blogs/devops/best-practices-working-with-self-hosted-github-action-runners-at-scale-on-aws/).

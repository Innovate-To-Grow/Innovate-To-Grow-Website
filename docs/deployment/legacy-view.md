# Legacy read-only viewer rollout and recovery

This runbook moves `legacy.i2g.ucmerced.edu` behind an authenticated,
read-only CloudFront gateway launched from the production I2G Django admin. It
keeps EC2 instance `i-0f06723e3677e7f24` and its Elastic IP for recovery, but
removes every public Web ingress rule after the private path is proven.

Do not combine the private-path rollout and public shutdown into one change.
`LEGACY_VIEW_ENABLED=false` is the fail-safe default and must remain false
until the snapshots, ACM renewal, private origin, CloudFront gateway, and
authorization tests have all passed.

## Managed and manual boundaries

[`aws/legacy/template.yaml`](../../aws/legacy/template.yaml) manages only:

- the same-region VPC peering connection;
- the two routes required by the production ECS and legacy EC2 subnets;
- TCP 8080 ingress from the production ECS security group to the legacy
  security group;
- the generated CloudFront-to-Django header in Secrets Manager;
- the AWS-assigned CloudFront distribution, no-cache/origin-request/security
  policies.

[`aws/legacy/monitoring-us-east-1.yaml`](../../aws/legacy/monitoring-us-east-1.yaml)
is a separate `us-east-1` stack containing the actionless CloudFront 5xx alarm.
CloudFront publishes `AWS/CloudFront` metrics only in that region; an alarm in
the `us-west-2` gateway stack would never receive the metric.

The stack intentionally does **not** manage the existing public Route53 record,
public legacy security-group rules, Nginx files, EC2 instance, EBS volumes, or
Elastic IP. Those existing resources are removed or edited only during the
explicit cutover steps below, which keeps rollback possible.

The production inventory verified on 2026-08-20 is:

| Resource | Value |
|---|---|
| AWS account / region | `394167325273` / `us-west-2` |
| Django VPC / CIDR | `vpc-0bdf6f90f9593cafa` / `10.2.0.0/16` |
| Django ECS route table | `rtb-0971181ab921a5eb3` |
| Django ECS security group | `sg-0c8cad5d34229f0d6` |
| Legacy VPC / CIDR | `vpc-067c86afb5ca877b0` / `172.31.0.0/16` |
| Legacy route table | `rtb-0beeb6cc1991fbc77` |
| Legacy instance private/public IP | `172.31.69.63` / `35.86.48.145` |
| Legacy security group | `sg-058c6e65ca6e2b7e4` |
| Root / data volumes | `vol-049077906745fd8da` / `vol-0cd55068afc6577cd` |
| Public hosted zone | `Z05097751AKPBGN5RW5GR` |
| API certificate | `arn:aws:acm:us-west-2:394167325273:certificate/b1cfb699-1b3a-4a35-bd4d-fe00b924baa5` |

Re-run the read-only inventory commands before rollout. Stop if an identifier,
CIDR, subnet association, current DNS value, or security-group rule differs
from this table.

```sh
aws ec2 describe-instances --region us-west-2 \
  --instance-ids i-0f06723e3677e7f24
aws ecs describe-services --region us-west-2 \
  --cluster itg-backend-cluster --services itg-backend-service
aws ec2 describe-route-tables --region us-west-2 \
  --route-table-ids rtb-0971181ab921a5eb3 rtb-0beeb6cc1991fbc77
aws ec2 describe-security-groups --region us-west-2 \
  --group-ids sg-0c8cad5d34229f0d6 sg-058c6e65ca6e2b7e4
aws ec2 describe-vpc-peering-connections --region us-west-2 \
  --filters Name=requester-vpc-info.vpc-id,Values=vpc-0bdf6f90f9593cafa \
            Name=accepter-vpc-info.vpc-id,Values=vpc-067c86afb5ca877b0
```

There must be no pre-existing peering connection or route to the peer CIDR. If
one exists, import/adopt it into the stack or remove the abandoned resource
through a separately reviewed change; do not let CloudFormation collide with
an unmanaged route.

## 1. Recovery snapshots and host backup

Create both snapshots and wait for both to become `completed` before touching
the host. Keep the returned snapshot IDs in the change record.

```sh
aws ec2 create-snapshot --region us-west-2 \
  --volume-id vol-049077906745fd8da \
  --description "I2G legacy root before private-view cutover" \
  --tag-specifications 'ResourceType=snapshot,Tags=[{Key=Name,Value=i2g-legacy-root-pre-private-view},{Key=InstanceId,Value=i-0f06723e3677e7f24}]'
aws ec2 create-snapshot --region us-west-2 \
  --volume-id vol-0cd55068afc6577cd \
  --description "I2G legacy data before private-view cutover" \
  --tag-specifications 'ResourceType=snapshot,Tags=[{Key=Name,Value=i2g-legacy-data-pre-private-view},{Key=InstanceId,Value=i-0f06723e3677e7f24}]'
aws ec2 wait snapshot-completed --region us-west-2 \
  --snapshot-ids <root-snapshot-id> <data-snapshot-id>
```

Confirm that SSH or EC2 Instance Connect works using one of the existing,
restricted TCP 22 sources. The live application was verified at
`/home/i2g-double-mail/test`, its uWSGI configuration is under `/var/www`, the
HTTP-facing Nginx upstream is uWSGI on `127.0.0.1:5001`, and the active SQLite
database is `/home/i2g-double-mail/test/project/db/data.sqlite3`. On the host,
capture the effective Nginx and service configuration, mounts, and listeners:

```sh
sudo nginx -T > /var/tmp/nginx-before-legacy-private-view.txt
sudo ss -lntp > /var/tmp/listeners-before-legacy-private-view.txt
sudo findmnt --real > /var/tmp/mounts-before-legacy-private-view.txt
sudo systemctl list-units --type=service --state=running > /var/tmp/services-before-legacy-private-view.txt
sudo test -r /home/i2g-double-mail/test/project/db/data.sqlite3
```

Use SQLite's online backup command for the discovered live database instead of
copying a possibly changing database file. Also archive the application and
Nginx configuration to the attached data volume. Record the exact paths in the
change ticket.

```sh
sudo sqlite3 /home/i2g-double-mail/test/project/db/data.sqlite3 \
  ".backup '/absolute-data-volume-path/i2g-legacy-pre-private-view.sqlite3'"
sudo tar --xattrs --acls -czf \
  /absolute-data-volume-path/i2g-legacy-config-pre-private-view.tgz \
  /etc/nginx /var/www /home/i2g-double-mail/test
```

Do not continue until the backup opens successfully with `sqlite3 ...
'PRAGMA integrity_check;'` and returns `ok`.

## 2. Confirm API TLS renewal

CloudFront uses `https://api.i2g.ucmerced.edu` as its only origin. The current
certificate is issued, but its managed renewal reported `PENDING_VALIDATION` on
2026-08-20. The required validation record is:

```text
_6579097737f18213214dd4a73fe79711.api.i2g.ucmerced.edu. CNAME
_3ab22ab930f33ff27415b0da50a98cb7.jkddzztszm.acm-validations.aws.
```

The record was present in hosted zone `Z05097751AKPBGN5RW5GR` when this runbook
was written. Do not replace it or create a duplicate. Check until
`RenewalSummary.RenewalStatus` is `SUCCESS`:

```sh
aws acm describe-certificate --region us-west-2 \
  --certificate-arn arn:aws:acm:us-west-2:394167325273:certificate/b1cfb699-1b3a-4a35-bd4d-fe00b924baa5 \
  --query 'Certificate.{Status:Status,RenewalEligibility:RenewalEligibility,RenewalStatus:RenewalSummary.RenewalStatus,Validation:RenewalSummary.DomainValidationOptions}'
```

If ACM still reports pending after DNS has propagated, resolve that certificate
incident before creating CloudFront. Do not bypass it with HTTP origin traffic.

## 3. Deploy application code disabled

Deploy the database migration and application changes to production while the
feature remains disabled. Configure these GitHub Environment values in
`AWS ECS - Prod`:

| Kind | Name | Initial value |
|---|---|---|
| Variable | `LEGACY_VIEW_ENABLED` | `false` |
| Variable | `LEGACY_ORIGIN_URL` | `http://172.31.69.63:8080` |
| Variable | `LEGACY_ORIGIN_HEADER_NAME` | `X-I2G-Legacy-Origin-Secret` |
| Variable | `LEGACY_CONNECT_TIMEOUT_SECONDS` | `3` |
| Variable | `LEGACY_READ_TIMEOUT_SECONDS` | `15` |

Leave `LEGACY_VIEWER_URL` and `LEGACY_ORIGIN_HEADER_SECRET_ARN` unset until the
stack outputs exist. Do not enable these settings in `AWS ECS(DEMO) - Prod`.
The backend workflow also enforces this boundary: every demo matrix render
forces the feature false, clears the private/viewer URLs and header reference,
and removes the legacy secret even if a repository-level variable is set.
After deployment, verify migrations completed and `/admin/legacy-view/` does not
offer a launch action while disabled.

## 4. Add the private Nginx listener

The existing public Nginx server block
`/etc/nginx/sites-enabled/legacy.i2g.ucmerced.edu` uses uWSGI on
`127.0.0.1:5001`. The private listener must use that same loopback upstream;
never point port 8080 at a host outside this instance.

The deployable files are versioned under [`aws/legacy/nginx`](../../aws/legacy/nginx).
Transfer those exact artifacts from the approved commit and install them with
root ownership; do not assemble the remote files by copying fragments from this
runbook:

```sh
scp aws/legacy/nginx/i2g-legacy-readonly-uwsgi.conf \
    aws/legacy/nginx/i2g-legacy-private-readonly.conf \
    ubuntu@35.86.48.145:/tmp/
ssh ubuntu@35.86.48.145
sudo install -o root -g root -m 0644 \
  /tmp/i2g-legacy-readonly-uwsgi.conf \
  /etc/nginx/snippets/i2g-legacy-readonly-uwsgi.conf
sudo install -o root -g root -m 0644 \
  /tmp/i2g-legacy-private-readonly.conf \
  /etc/nginx/conf.d/i2g-legacy-private-readonly.conf
sudo rm /tmp/i2g-legacy-readonly-uwsgi.conf /tmp/i2g-legacy-private-readonly.conf
```

The tracked uWSGI snippet below keeps forwarding directives in one
non-location file so the four positive path rules cannot drift:

```nginx
include uwsgi_params;
uwsgi_pass i2g_legacy_application;
uwsgi_param HTTP_HOST legacy.i2g.ucmerced.edu;
uwsgi_param HTTP_X_FORWARDED_PROTO https;
uwsgi_param HTTP_X_FORWARDED_FOR $remote_addr;
uwsgi_param HTTP_AUTHORIZATION "";
uwsgi_param HTTP_COOKIE "";
uwsgi_hide_header Set-Cookie;
uwsgi_connect_timeout 3s;
uwsgi_read_timeout 15s;
uwsgi_send_timeout 15s;
```

The tracked private listener is:

```nginx
map $request_method $i2g_legacy_read_method {
    default 0;
    GET  1;
    HEAD 1;
}

# Deliberately omit $request and $args so search/query values are not logged.
log_format i2g_legacy_private '$remote_addr - [$time_local] '
                              '"$request_method $uri $server_protocol" '
                              '$status $body_bytes_sent rt=$request_time';

upstream i2g_legacy_application {
    server 127.0.0.1:5001;
}

server {
    listen 172.31.69.63:8080;
    server_name _;

    access_log /var/log/nginx/i2g-legacy-private-access.log i2g_legacy_private;
    error_log  /var/log/nginx/i2g-legacy-private-error.log warn;

    allow 10.2.0.0/16;
    deny all;

    if ($i2g_legacy_read_method = 0) {
        return 405;
    }

    # Retired Flask-Admin and write routes: mirror _BLOCKED_PREFIXES in
    # src/apps/core/legacy_view/policies.py. /event itself is informational;
    # only descendants of /event are blocked.
    location ~* ^/(?:admin|catch_bounces|confirm|contact|documentation|edit_form|event-registration|events|full-registration|info-form|manual_email|membership|otp|project-submission|prospects|resend|resend-page|signup|tracking_pixel|update|user)(?:/|$) {
        return 410;
    }
    location ~* ^/event/ {
        return 410;
    }
    location ~* ^/static/admin(?:/|$) {
        return 410;
    }
    # I2G_LEGACY_BLOCKED_STATIC_PATHS
    location ~* ^/static/(?:images/tracking_pixel\.png|js/js-siteimprove\.js|js/recaptcha-api\.js)$ {
        return 410;
    }

    # Audited historical/information pages.
    location = / {
        include /etc/nginx/snippets/i2g-legacy-readonly-uwsgi.conf;
    }
    location ~* ^/(?:2014-sponsors|2015-sponsors|2020-fall-post-event|2021-fall-event|2021-spring-event|2022-fall-event|2022-spring-event|2023-fall-event|2023-spring-event|2024-fall-event|2024-spring-event|2025-fall-event|2025-spring-event|about|about_engsl|acknowledgement|attendees|capstone-purchasing-reimbursement|contact-us|current-projects|engineering-capstone|event|faqs|ferpa|home-during-event|home-post-event|i2g-project-sponsor-acknowledgement|i2g-student-agreement|i2g-students-preparation|judges|judging|partnership|past-events|past-projects|privacy|projects|projects-teams|sample-proposals|schedule|software-capstone|sponsorship|students|template|template-email-team-students|video-preparation)$ {
        include /etc/nginx/snippets/i2g-legacy-readonly-uwsgi.conf;
    }

    # Audited read-only API and UUID detail routes.
    location ~* ^/api/(?:current-projects|schedule-data)$ {
        include /etc/nginx/snippets/i2g-legacy-readonly-uwsgi.conf;
    }
    location ~* "^/past-projects/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$" {
        include /etc/nginx/snippets/i2g-legacy-readonly-uwsgi.conf;
    }

    # Static assets needed by the audited pages, after the explicit static
    # denylist above.
    location ~* ^/static/.+ {
        include /etc/nginx/snippets/i2g-legacy-readonly-uwsgi.conf;
    }

    # Unknown paths fail closed and never reach Flask/uWSGI.
    location / {
        return 404;
    }
}
```

This is defense in depth; Django remains the authoritative audited path and
method allowlist. Any future read route must be added to the Django policy and
this Nginx positive allowlist in the same reviewed change. A route present in
only one layer remains unavailable.

Validate and reload without stopping Nginx:

```sh
sudo nginx -t
sudo systemctl reload nginx
sudo ss -lntp | grep '172.31.69.63:8080'
test "$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' \
  http://172.31.69.63:8080/)" = 403
```

The local request is deliberately denied because the listener allows only the
production ECS CIDR. Port 8080 is not yet reachable from ECS because its
security-group rule and routes belong to the stack deployed next. Validate the
200/405/410/404 behavior through the Django proxy after peering is active;
never weaken this allowlist merely to run a host-local probe.

## 5. Validate and deploy the private gateway stack

Local and CI validation is credential-free:

```sh
cfn-lint aws/legacy/template.yaml aws/legacy/monitoring-us-east-1.yaml
python scripts/ci/validate_legacy_infrastructure.py
python aws/validate_backend_task_definition.py aws/task-definition.json
```

Then ask AWS to validate the template and deploy it in `us-west-2`:

```sh
aws cloudformation validate-template --region us-west-2 \
  --template-body file://aws/legacy/template.yaml
aws cloudformation validate-template --region us-east-1 \
  --template-body file://aws/legacy/monitoring-us-east-1.yaml
aws cloudformation deploy --region us-west-2 \
  --stack-name i2g-legacy-view \
  --template-file aws/legacy/template.yaml \
  --parameter-overrides \
    ApplicationVpcId=vpc-0bdf6f90f9593cafa \
    ApplicationVpcCidr=10.2.0.0/16 \
    ApplicationRouteTableId=rtb-0971181ab921a5eb3 \
    ApplicationSecurityGroupId=sg-0c8cad5d34229f0d6 \
    LegacyVpcId=vpc-067c86afb5ca877b0 \
    LegacyVpcCidr=172.31.0.0/16 \
    LegacyRouteTableId=rtb-0beeb6cc1991fbc77 \
    LegacySecurityGroupId=sg-058c6e65ca6e2b7e4 \
    BackendOriginDomainName=api.i2g.ucmerced.edu \
    BackendOriginPath=/legacy-view \
  --no-fail-on-empty-changeset
```

Wait for the distribution status to become `Deployed`, then capture all stack
outputs:

```sh
aws cloudformation describe-stacks --region us-west-2 \
  --stack-name i2g-legacy-view --query 'Stacks[0].Outputs'
aws cloudfront wait distribution-deployed \
  --id <LegacyDistributionId-output>
```

Deploy the monitoring stack in `us-east-1`, passing the exact distribution ID
from the preceding output:

```sh
aws cloudformation deploy --region us-east-1 \
  --stack-name i2g-legacy-view-monitoring \
  --template-file aws/legacy/monitoring-us-east-1.yaml \
  --parameter-overrides DistributionId=<LegacyDistributionId-output> \
  --no-fail-on-empty-changeset
aws cloudformation describe-stacks --region us-east-1 \
  --stack-name i2g-legacy-view-monitoring --query 'Stacks[0].Outputs'
```

The ECS **execution role** (not only the application task role) must have
`secretsmanager:GetSecretValue` for the exact
`LegacyOriginHeaderSecretArn` output so the ECS agent can inject the value.
The stack names the secret `itg/backend/legacy-view-origin-header` to stay under
the existing backend secret namespace, but an operator with IAM policy-inspect
access must still verify `ecsTaskExecutionRole` covers the generated ARN before
deployment. If it does not, add only that exact ARN; do not grant a wildcard
secret resource. The renderer removes this secret from the background worker,
so only the Web container receives it.

Set the following additional variables in `AWS ECS - Prod`, but keep the
feature disabled:

| Kind | Name | Value |
|---|---|---|
| Variable | `LEGACY_VIEWER_URL` | `LegacyViewerUrl` stack output |
| Variable | `LEGACY_ORIGIN_HEADER_SECRET_ARN` | `LegacyOriginHeaderSecretArn` stack output |

Deploy production once more with `LEGACY_VIEW_ENABLED=false`. The ECS task
definition validator will reject a literal secret, an invalid secret ARN, an
unbounded timeout, a non-private origin, or an enabled non-CloudFront viewer
URL.

From a production ECS task, verify the private listener is reachable and the
blocked routes remain blocked. If ECS Exec is already enabled, this is a
read-only probe:

```sh
aws ecs execute-command --region us-west-2 \
  --cluster itg-backend-cluster \
  --task <running-production-task-arn> \
  --container itg-backend --interactive \
  --command "python -c \"import urllib.request; print(urllib.request.urlopen('http://172.31.69.63:8080/').status)\""
```

Do not enable ECS Exec solely for this change. Use an already approved VPC
probe if it is not available.

## 6. Enable and test the authenticated viewer

Set `LEGACY_VIEW_ENABLED=true` only in `AWS ECS - Prod`, deploy, and complete all
of these checks before changing public DNS or ingress:

1. Anonymous CloudFront GET/HEAD and direct
   `https://api.i2g.ucmerced.edu/legacy-view/` access return no legacy content.
2. A staff account without `core` permission receives 403 at
   `/admin/legacy-view/`.
3. A Core administrator launches the CloudFront page without a second login.
4. An invalid, expired, or reused exchange code fails; two concurrent exchanges
   of one code produce exactly one success.
5. Historical pages, safe query-string navigation, static assets, Range reads,
   and reviewed GET APIs work.
6. `/admin/`, `/membership/`, `/update/`, `/confirm/`, `/tracking_pixel/`, and
   every non-exchange write request never reach the legacy application.
7. Logging out of Admin, removing `core`, or deactivating the account
   invalidates the existing viewer session on its next request.
8. The browser receives only `i2g_legacy_viewer` for the CloudFront domain; the
   API `sessionid`, Authorization, CSRF cookie, and legacy `Set-Cookie` are not
   forwarded.
9. Origin failures return a generic 502 without an internal URL, secret, stack
   trace, or server banner.

CloudFront forwards query strings to the fixed Django gateway for historical
navigation, but forwards only the `i2g_legacy_viewer` cookie and a small safe
header allowlist (`Accept`, `Accept-Language`, exchange `Content-Type`, and the
three conditional-read headers). It does not forward the viewer `Host`,
`Authorization`, `Origin`, `Referer`, or `User-Agent` header. CloudFront handles
`Range` itself and edge compression is disabled so byte-range semantics remain
stable. Caching and browser storage are disabled with zero TTL and
`Cache-Control: no-store, private`.

## 7. Remove the old public entry point

Export the current Route53 record before deleting it:

```sh
aws route53 list-resource-record-sets \
  --hosted-zone-id Z05097751AKPBGN5RW5GR \
  --query 'ResourceRecordSets[?Name==`legacy.i2g.ucmerced.edu.`]'
```

Delete exactly the existing record, then wait at least its 300-second TTL:

```sh
aws route53 change-resource-record-sets \
  --hosted-zone-id Z05097751AKPBGN5RW5GR \
  --change-batch '{"Comment":"Retire public I2G legacy hostname","Changes":[{"Action":"DELETE","ResourceRecordSet":{"Name":"legacy.i2g.ucmerced.edu.","Type":"A","TTL":300,"ResourceRecords":[{"Value":"35.86.48.145"}]}}]}'
```

Then remove only the four verified public Web ingress rules. Preserve the
three restricted TCP 22 rules, the Elastic IP, the instance, and both volumes:

```sh
for port in 80 443 3000 5000; do
  aws ec2 revoke-security-group-ingress --region us-west-2 \
    --group-id sg-058c6e65ca6e2b7e4 \
    --protocol tcp --port "$port" --cidr 0.0.0.0/0
done
```

After the security-group change, disable the old Nginx 80/443 server block and
its Certbot renewal hook, but keep the private 8080 configuration. Test and
reload Nginx. From outside AWS, verify the old hostname and EIP cannot establish
connections on 80, 443, 3000, or 5000 even when the old Host header is forced.
From Django ECS, re-run the 8080 and authenticated CloudFront checks.

Do not add a public redirect from the old hostname. Do not change
`archive.i2g.ucmerced.edu`, the demo environment, the Elastic IP association,
or instance lifecycle in this rollout.

## Monitoring and secret handling

- The `LegacyDistribution5xxAlarmName` output comes from the separate
  `us-east-1` monitoring stack and is intentionally actionless, so it cannot
  publish into an unapproved notification destination. Attach an alarm action
  only through the normal monitored-alerting change process.
- Watch CloudFront `5xxErrorRate` and structured Django gateway logs during the
  first hour. Logs may contain route, status, duration, byte count, and an
  opaque viewer/session identifier; they must never contain the exchange code,
  shared origin header, cookies, or upstream query values.
- CloudFront resolves the Secrets Manager dynamic reference when its
  distribution configuration is created or updated. Secret rotation therefore
  requires one coordinated change: generate the new secret, update CloudFront
  so it resolves the new value, deploy ECS with the same secret version, test,
  and only then retire the old value. Do not rotate by editing the secret alone.
- Run CloudFormation drift detection after rollout. Treat changes to peering,
  either route, TCP 8080 ingress, the origin header, cache policy, or forwarded
  cookie list as security-sensitive drift.

## Rollback

Choose the smallest rollback that restores a known safe state.

### Before public shutdown

Set `LEGACY_VIEW_ENABLED=false` and redeploy. The private stack and Nginx 8080
listener may remain in place while the issue is diagnosed. This removes the
Admin launch path without restoring public access.

If the stack itself failed, let CloudFormation finish rollback, inspect stack
events, and fix the template or conflicting unmanaged route. The shared header
secret is retained by policy. Never manually delete a route or peering resource
while CloudFormation still owns it.

### After public shutdown

First set `LEGACY_VIEW_ENABLED=false`. If an approved incident decision requires
temporary restoration of the old public site:

1. restore the backed-up public Nginx 80/443 configuration and pass `nginx -t`;
2. authorize only public 80 and 443 on `sg-058c6e65ca6e2b7e4` (do not reopen
   3000 or 5000);
3. recreate the exact Route53 A record with TTL 300 and value `35.86.48.145`;
4. confirm the public TLS certificate and page before announcing recovery.

Leave the private stack intact unless it is the cause. If it must be removed,
disable and deploy Django first, delete the `us-east-1` monitoring stack, and
only then delete the `us-west-2` gateway stack; its retained secret will need
explicit, separately approved cleanup later.

### Host or data recovery

Restore Nginx/application configuration from the archived files. For data loss,
stop the legacy application before replacing the SQLite database, or restore
the two EBS snapshots to new volumes and attach them for inspection. Do not
overwrite the original volumes until snapshot contents and mount mapping have
been verified. The instance, Elastic IP, and `DeleteOnTermination=false`
volumes remain available specifically for this recovery path.

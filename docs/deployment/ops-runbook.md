# Operations runbook (skeleton)

The outline of the I2G operations runbook: what an operator needs to keep the site running, renew what expires,
deploy and roll back, and respond to incidents. It links to the procedures that are already public.

> **Skeleton only. Do not fill in values here.** This repository is public. Account IDs, ARNs and resource names,
> hostnames, IP addresses, credentials, people's names and contacts, and ticket numbers go in the **private ops
> doc**. Every place below marked **→ private ops doc** says what the private document records. Placeholders marked
> **TODO** are procedures still to be written.

Where the private ops doc lives, and who may read and edit it: **→ private ops doc** (decision pending: a private
repository or a restricted UC Merced Drive/Box folder).

## 1. Systems and owners

| System | What runs there | Owner (role) | Values |
|---|---|---|---|
| AWS account | Backend and archive containers, background worker, database, file storage, Amplify (frontend), SES, SMS, Bedrock, Secrets Manager, WAF | I2G AWS account owner | Account, region, resource names, console access → private ops doc |
| Microsoft 365 / Entra | The i2g@ucmerced.edu mailbox; the app registration used to send and read it | UC Merced OIT (Cloud Systems); I2G owns the mailbox | App and tenant IDs, access-policy details, approval ticket → private ops doc |
| Google Cloud / Workspace | Sheets syncs (service account), Gmail API and IMAP accounts | I2G | Project, service accounts, account owners → private ops doc |
| GitHub | Code, CI, deploy workflows, production approval | I2G web team | Organisation admins, environment reviewers → private ops doc |
| DNS and campus network | The site's domain names; campus egress ranges for the WAF | UC Merced OIT | Records, ranges, contacts → private ops doc |
| CI runner fleet (optional) | Self-hosted CI runners | I2G web team | Account, network, state storage → private ops doc |

## 2. Access

Who holds each kind of access, and how to grant or remove it. **→ private ops doc** for the names.

- Admin console: the I2G Master account(s) and staff section grants (see the
  [staff handbook](../staff/README.md)). Review every term.
- AWS console and CLI access (SSO roles).
- GitHub organisation, repository and `production` environment reviewers.
- Entra app owners (OIT) and the mailbox's delegates.
- Google Cloud project owners.

**TODO:** the joiner/leaver checklist (what to grant, what to revoke, in which order).

## 3. Expiry and renewal calendar

Put each date in a shared calendar with a reminder well before it. Keep the calendar's link in the private ops doc.

| Item | Expires / renews | Warning | Procedure |
|---|---|---|---|
| Microsoft Graph app certificate | **2027-10-29** | The site logs a warning from 60 days before and shows an amber badge; red and a failing `verify_service_configs --strict` from 14 days before | [Rotate the certificate](../integrations/microsoft-graph-email.md#rotate-the-certificate) |
| Gmail API service-account key | Does not expire by default; rotation date → private ops doc | None | [Gmail API rotation](../integrations/gmail-api-email.md#rotation) |
| Shared AWS IAM key (SES, SMS, Bedrock) | Rotation date → private ops doc | None | [Application AWS credentials](production.md#application-aws-credentials-and-background-jobs) |
| Google Sheets service-account key | Rotation date → private ops doc | None | **TODO** |
| SMS origination number and its registration | Renewal dates and fees → private ops doc | None | **TODO** |
| TLS certificates (AWS managed) | Renew automatically | AWS notices | Check renewal status after DNS changes |
| Campus IP set for the WAF | Re-confirm every term | — | [Campus IP set](waf-rate-limits.md#1-campus-ip-set) |
| Admin access review | Every term | — | Section 2 |
| Staff handbook review | Every term | — | [Keeping this handbook current](../staff/README.md#keeping-this-handbook-current) |

## 4. Deploy and roll back

1. A pull request is reviewed and merged to `main`; CI runs the full suite.
2. After CI succeeds, the deploy workflows wait at the production approval gate
   ([Production deployment approval](production.md), [CI/CD](ci-cd.md)).
3. Before approving, check that the waiting run deploys the commit you expect (the current `main`). Approvers →
   private ops doc.
4. After the deploy, check: the public site loads; the admin loads; **Email Monitoring → Bounce processing** shows
   **Running** within about 10 minutes; a test email from **Email Sending Method** arrives.
5. **Roll back** by pointing the service back at the previous task definition revision. Database migrations are not
   undone by a rollback; check the release's migrations first. **TODO:** the exact commands; the current and
   previous revisions → private ops doc.

## 5. Background worker

It sends queued email and SMS, scans the mailbox for bounce reports, syncs Google Sheets and runs the hourly
clean-ups. Signs that it is down: **Bounce processing** shows "No recent successful scan"; campaigns stay
**Queued**.

**TODO:** how to check it, read its logs and restart it (log locations and service names → private ops doc).

## 6. Incident playbooks

Each playbook: symptoms, first checks, who to call, how to recover, what to record afterwards. Contacts → private
ops doc.

| Incident | First checks | Public reference |
|---|---|---|
| Email is not sending | **Delivery Rates** status line (paused or stopped?), **Email Monitoring** last error, the provider's access check | [Delivery rates](../integrations/delivery-rates.md), [Graph error reference](../integrations/microsoft-graph-email.md#error-reference) |
| A blast went to the wrong people or with the wrong content | Stop further sends (**TODO:** the procedure), **Revoke login links** on the campaign, tell the program lead | [Login link tokens](../cms-admin/member-and-mail-tools.md#login-link-tokens) |
| Many bounces or rejections after a blast | **Email Monitoring → Bounce reports**, the share of **Rejected** | [Email monitoring](../integrations/email-monitoring.md) |
| A credential may have leaked (Graph key, AWS key, Gmail key, admin account) | Revoke first, then investigate; CloudTrail; Admin Log | [Emergency revocation](../integrations/microsoft-graph-email.md#emergency-revocation) |
| The site is down or slow | Health checks, recent deploys, request limits | [Request limits](../integrations/request-limits.md) |
| SMS stopped (spend limit, throttling) | **Delivery Rates → AWS SMS** card | [Delivery rates](../integrations/delivery-rates.md) |
| Personal data exposed (an export shared, wrong recipients) | What, who, when; contain it | UC Merced privacy and InfoSec contacts → private ops doc |

**TODO:** write each playbook out.

## 7. Contacts and escalation

Roles only here; names, addresses and phone numbers → private ops doc.

- I2G program lead (business decisions, member communication).
- I2G web developer (site, deploys, this runbook).
- UC Merced OIT Cloud Systems (Entra app, Exchange mailbox, its sending limits).
- UC Merced InfoSec (security approvals, incidents).
- AWS account owner.
- Campus IT (DNS, campus address ranges).

## 8. Decisions and references

Record each decision with its date and where it was approved; ticket numbers → private ops doc. For example:

- The Microsoft Graph permissions the site runs with, and the InfoSec approval behind them.
- Bounce reports never change members or subscriptions automatically; every change is a staff action.
- A section grant gives full control of that section of the admin.
- The helpdesk starts in shadow mode (it records tickets and sends nothing).
- Retention periods: email records 180 days, bounce reports 365 days.

## 9. Routine checks

| When | Check |
|---|---|
| After every blast | **Email Monitoring** campaign row; bounce reports; (when live) **Bounced addresses** |
| Weekly | **Bounce processing** is **Running**; no stuck **Queued** campaigns; delivery limits not stopped |
| Monthly | Certificate and key expiry badges; CloudTrail access to the key secrets; AWS costs |
| Every term | Admin access review; campus IP set; this runbook and the staff handbook |

# Assistant Usage Dashboard

The usage dashboard surfaces Amazon Bedrock token/invocation consumption next to
the site's own conversation logs, so an operator can watch assistant activity on
a big screen at a glance.

- Admin route: **System Intelligence → Usage Dashboard** (`/admin/system-intelligence/usage/`).
- JSON feed: `/admin/system-intelligence/usage/data/` (`?force=1` bypasses the cache).

## What it shows

| Section | Source |
|---|---|
| Stat cards (24h input/output tokens, invocations, conversations today, messages 7d) | CloudWatch + local DB |
| Tokens — last 30 days (stacked input/output bars) | CloudWatch |
| Invocations — last 30 days | CloudWatch |
| Tokens by source (Public Chat / AI Search / Admin Chat) | local DB |
| By-model table (input/output/invocations) | CloudWatch |
| Recent conversations (links to the matching `AssistantConversationLog`) | local DB |
| Top prompts (30d) | local DB |

The CloudWatch numbers come from the free `AWS/Bedrock` namespace
(`InputTokenCount`, `OutputTokenCount`, `Invocations`), read per `ModelId`
dimension over a daily (`86400s` `Sum`) period.

## Cost Explorer is intentionally NOT used

This feature reads **only** CloudWatch. It never calls AWS Cost Explorer
(`ce:GetCostAndUsage` and friends) because those calls are billed per request.
All dollar/spend questions are deliberately out of scope — token and invocation
counts are free to read and are what the dashboard charts.

## IAM policy

Grant the active AWS Credential Config's IAM user read-only CloudWatch access:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockUsageMetricsRead",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricData",
        "cloudwatch:ListMetrics"
      ],
      "Resource": "*"
    }
  ]
}
```

When the permission (or the AWS credentials entirely) is missing, the dashboard
degrades gracefully: an amber banner explains the reason (`permission` or
`unconfigured`) and the local DB sections still render.

## Caching

The merged context is cached in Django's cache:

| Key | TTL | Contents |
|---|---|---|
| `assistant:usage:cloudwatch` | 600s | CloudWatch metrics (slow-changing AWS read) |
| `assistant:usage:local` | 300s | DB aggregates |

The data endpoint with `?force=1` recomputes both halves and re-warms the cache.

## TV / big-screen mode

The **Fullscreen** button requests browser fullscreen and applies a `si-tv-mode`
class that enlarges the type and hides the admin chrome. While fullscreen, the
page polls `/admin/system-intelligence/usage/data/?force=1` every 60 seconds and
rebuilds the charts in place — handy for an always-on office display. Exiting
fullscreen stops the polling.

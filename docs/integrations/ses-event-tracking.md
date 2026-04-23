# AWS SES Event Tracking (Bounces, Complaints, Deliveries)

This doc is an operator runbook. It covers the AWS-side configuration required
for `RecipientLog` to reflect the real delivery outcome of campaign emails.
Without it, `send_raw_email` returning 200 only proves SES *accepted* the
message — recipients that bounce or mark it as spam never update the log.

## Data flow

```
campaign sender (send_raw_email)        SES                AWS SNS
        │  ConfigurationSetName        │                    │
        ▼                              ▼                    │
  RecipientLog                    event destination ────────▶ HTTPS subscription
  status="sent"                                               │
  ses_message_id=X                                            ▼
                                                     /mail/ses/events/
                                                     (signature verified →
                                                      RecipientLog.status
                                                      = bounced / complained / delivered)
```

Code entry points:

- Sender tags every send with `ConfigurationSetName`: `src/mail/services/send_campaign.py::_send_via_ses`
- Webhook: `src/mail/views.py::SesEventWebhookView` mounted at `/mail/ses/events/`
- Signature verifier: `src/mail/services/sns_signature.py`
- Event dispatcher: `src/mail/services/ses_events.py`

## AWS setup — one-time per environment

### 1. Create a configuration set

AWS Console → SES → Configuration sets → Create set.

- Name: `i2g-production` (or `i2g-staging`).
- Reputation metrics: enabled.
- Suppression list: default (SES-account level).

Set `SES_CONFIGURATION_SET_NAME=i2g-production` in the ECS/Amplify environment.

### 2. Create an SNS topic

AWS Console → SNS → Topics → Create standard topic. Name: `i2g-ses-events`.
Set `SES_SNS_TOPIC_ARN` to the resulting ARN (`arn:aws:sns:us-west-2:<account>:i2g-ses-events`).
The webhook will enforce this as an allowlist against incoming `TopicArn`.

### 3. Wire the configuration set to the SNS topic

SES → Configuration sets → `i2g-production` → Event destinations → Add destination.

- Destination type: SNS.
- SNS topic: `i2g-ses-events`.
- Event types — enable: `Bounce`, `Complaint`, `Delivery`, `DeliveryDelay`, `Reject`.
  (`Send`, `Open`, `Click` are optional; the dispatcher accepts them as no-ops.)

### 4. Subscribe the webhook

SNS → Topics → `i2g-ses-events` → Create subscription.

- Protocol: HTTPS.
- Endpoint: `https://api.i2g.ucmerced.edu/mail/ses/events/` (replace host per env).

The endpoint auto-confirms the subscription: our dispatcher receives the
`SubscriptionConfirmation` message and hits `SubscribeURL` (validated to the
`.amazonaws.com` domain first). The subscription should flip to `Confirmed`
within seconds; the server log shows `SNS subscription confirmed for topic ...`.

**Recommended:** configure a redrive policy (DLQ) on the subscription so
transient outages don't drop events.

## Verification with the SES simulator

Production-safe recipients that AWS guarantees to trigger specific event
types (won't hit real mailboxes, no reputation impact):

| Address | Event |
| --- | --- |
| `success@simulator.amazonses.com` | `Delivery` |
| `bounce@simulator.amazonses.com` | `Bounce` / `Permanent` |
| `ooto@simulator.amazonses.com` | `Bounce` / `Transient` (out-of-office) |
| `complaint@simulator.amazonses.com` | `Complaint` |
| `suppressionlist@simulator.amazonses.com` | `Bounce` with SES suppression-list subtype |

Send a tiny test campaign addressed to these and watch
`/admin/mail/recipientlog/` — each row should flip from `sent` to its
terminal status within ~5 seconds.

## Security

The webhook is intentionally public (AWS cannot present credentials). Trust
is anchored in two checks in `SesEventWebhookView`:

1. **SNS signature verification** — the envelope is signed by AWS with a
   cert served only from `*.amazonaws.com`. Tampering with any signed field
   is rejected with 403. Certs are fetched via `https` with the host
   restricted by allowlist to prevent SSRF.
2. **`TopicArn` allowlist** — when `SES_SNS_TOPIC_ARN` is set, envelopes
   from any other topic are rejected. This contains the blast radius if
   another SNS topic is misconfigured to point at us.

The endpoint also has a DRF throttle at 600/minute per source IP
(`ses_events` scope) as defense-in-depth against signed-envelope replay.

## What this does NOT do (out of scope for now)

- Auto-unsubscribing a member's `ContactEmail` after a hard bounce.
- Backfilling `ses_message_id` for pre-existing rows.
- Recomputing `EmailCampaign.sent_count` / `failed_count` on late bounces —
  those counters preserve moment-of-send semantics; per-row `RecipientLog`
  is the source of truth for deliverability.

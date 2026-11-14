"""
Per-channel seeds for ``DELIVERY_RATES["channels"]``.

Each value seeds the channel's ``DeliveryRatePolicy`` row (Mail → Delivery Rates), and every documented provider
limit here is also its ceiling: staff can lower it there, never raise it. A deployer whose provider grants more
(an AWS quota increase, a larger Google project quota) raises it with ``DELIVERY_RATES_OVERRIDES``.

Rates are in the channel's unit (``DeliveryRatePolicy.Channel``): per minute for Graph, SMTP, IMAP and the Gmail
API, per second for SES (recipients) and SMS (messages). ``None`` means "not documented": the provider reports it
at runtime, or Smart rate falls back to ``fallback_rate``.

Keys every channel has:
  smart_enabled             – seed of the Smart rate switch (on for every channel).
  manual_rate               – seed of the rate used while Smart rate is off.
  provider_limit            – documented rate limit: seed and ceiling of the policy field.
  fallback_rate             – what Smart rate assumes when no limit is known at all (labelled "limit unknown").
  headroom                  – share of the bound Smart rate uses (room for traffic the site cannot see).
  burst                     – most requests sent back to back; clipped so rate + burst never exceeds the bound.
  recovery_interval_seconds – Smart rate speeds up one recovery step per interval after a slowdown.
  backoff_*_seconds         – pause after a throttle that names no Retry-After, doubling up to the maximum.
Sending channels also have the rolling-24 h ``daily_limit`` (budget units: recipients), ``budget_headroom`` (share
of every daily limit the site uses) and ``transactional_reserve`` (``None`` = the ``lanes`` default).
"""

from .sending_channels import GMAIL_API_SEND, GRAPH_SEND, SES_SEND, SMS_SEND, SMTP_SEND

# Sources, cited by name in the comments below.
# Microsoft: "Exchange Online limits" (sending limits per mailbox).
_EXCHANGE_LIMITS = "https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits"
# Microsoft: outbound spam policy, Standard preset.
_OUTBOUND_SPAM = "https://learn.microsoft.com/en-us/defender-office-365/recommended-settings-for-eop-and-office365#outbound-spam-policy-settings"
# Microsoft Graph service limits (Outlook: per app ID and mailbox).
_GRAPH_THROTTLING = "https://learn.microsoft.com/en-us/graph/throttling-limits"
# Amazon SES sending quotas, their errors, and GetAccount.
_SES_QUOTAS = "https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas.html"
_SES_QUOTA_ERRORS = "https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas-errors.html"
_SES_GET_ACCOUNT = "https://docs.aws.amazon.com/ses/latest/APIReference-V2/API_GetAccount.html"
# Google Workspace: Gmail SMTP server and SMTP relay limits.
_GMAIL_SMTP = "https://knowledge.workspace.google.com/admin/gmail/send-email-from-a-printer-scanner-or-app"
_GMAIL_RELAY = (
    "https://knowledge.workspace.google.com/admin/gmail/advanced/route-outgoing-smtp-relay-messages-through-google"
)
# Google: IMAP clients per account, and the bandwidth limits that suspend IMAP.
_GMAIL_IMAP_CLIENTS = "https://support.google.com/mail/answer/7126229"
_GMAIL_BANDWIDTH = "https://knowledge.workspace.google.com/admin/gmail/gmail-bandwidth-limits"
# Google: Gmail API quota units, Workspace sending limits, and Gmail API error handling.
_GMAIL_API_QUOTA = "https://developers.google.com/workspace/gmail/api/reference/quota"
_GMAIL_SENDING_LIMITS = "https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace"
_GMAIL_API_ERRORS = "https://developers.google.com/workspace/gmail/api/guides/handle-errors"
# AWS End User Messaging SMS: account quotas and per-number MPS.
_SMS_QUOTAS = "https://docs.aws.amazon.com/sms-voice/latest/userguide/quotas.html"
_SMS_MPS = "https://docs.aws.amazon.com/sms-voice/latest/userguide/sms-limitations-mps-view.html"


GRAPH_READ = {
    "smart_enabled": True,
    # App default for the admin inbox and the access check.
    "manual_rate": 60,
    # _GRAPH_THROTTLING, Outlook service: 10,000 requests per 10 minutes per app ID and mailbox.
    "provider_limit": 1_000,
    "fallback_rate": None,
    # App default: reads share Outlook's per-mailbox allowance with sends, so they use only half of it.
    "headroom": 0.5,
    "burst": 3,
    "recovery_interval_seconds": 600,
    "backoff_initial_seconds": 5,
    "backoff_max_seconds": 120,
}


GMAIL_IMAP = {
    "smart_enabled": True,
    # App default: login sessions per minute for the admin inbox and "Import from Gmail".
    "manual_rate": 10,
    # Not documented: Google publishes no IMAP rate.
    "provider_limit": None,
    # App default (labelled "limit unknown"); _GMAIL_IMAP_CLIENTS: "up to 15 email clients at a time per account".
    "fallback_rate": 30,
    "headroom": 1.0,
    "burst": 3,
    "recovery_interval_seconds": 600,
    "backoff_initial_seconds": 60,
    "backoff_max_seconds": 3_600,
    # App default: socket timeout of each IMAP session.
    "timeout_seconds": 30,
    # App default: pause after "Too many simultaneous connections" (Google gives no lockout time).
    "connections_pause_seconds": 60,
    # _GMAIL_BANDWIDTH: a bandwidth suspension "typically lasts for 1 hour, but can last up to 24 hours".
    "bandwidth_breaker_seconds": 3_600,
}


CHANNELS = {
    "graph_send": GRAPH_SEND,
    "graph_read": GRAPH_READ,
    "ses_send": SES_SEND,
    "smtp_send": SMTP_SEND,
    "gmail_imap": GMAIL_IMAP,
    "gmail_api_send": GMAIL_API_SEND,
    "sms_send": SMS_SEND,
}

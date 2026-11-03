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

# Microsoft Graph: provider_limit, daily_limit, the hourly limits and max_recipients_per_message seed the sending
# limits of MicrosoftGraphProviderConfig (the Core admin page) and apply only while no active Graph configuration
# exists; the values entered there are what the channel uses (apps.core.services.delivery_rates.rules.tenant).
GRAPH_SEND = {
    "smart_enabled": True,
    # App default: 80 % of the provider limit (the PR #643 value), so login codes keep room during campaigns.
    "manual_rate": 24,
    # _EXCHANGE_LIMITS: "Message rate limit" 30 messages per minute per mailbox.
    "provider_limit": 30,
    "fallback_rate": None,
    # App default: staff also send from this mailbox in Outlook, which shares the 30/min the site cannot see.
    "headroom": 0.8,
    "burst": 3,
    "recovery_interval_seconds": 600,
    # Microsoft sends Retry-After with its throttles; this is only for a throttle without one.
    "backoff_initial_seconds": 5,
    "backoff_max_seconds": 120,
    # _EXCHANGE_LIMITS: "Recipient rate limit" 10,000 recipients per day.
    "daily_limit": 10_000,
    # _EXCHANGE_LIMITS: "Recipient limit" 500 recipients per message (the tenant can set up to 1,000); OIT states
    # 500 for i2g@ucmerced.edu (2026-11-03).
    "max_recipients_per_message": 500,
    # _OUTBOUND_SPAM, Standard preset: RecipientLimitExternalPerHour 500, RecipientLimitInternalPerHour 1,000.
    "hourly_external_limit": 500,
    "hourly_internal_limit": 1_000,
    # Until staff confirm the tenant's real outbound spam policy ("Tenant limits confirmed")...
    "limits_confirmed": False,
    # ...campaigns stay under the Standard preset's RecipientLimitPerDay of 1,000 (_OUTBOUND_SPAM): its default
    # action, BlockUserForToday, would also stop login codes.
    "unconfirmed_bulk_daily_limit": 1_000,
    "budget_headroom": 1.0,
    "transactional_reserve": None,
}

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

SES_SEND = {
    "smart_enabled": True,
    # EmailServiceConfig.max_send_rate's model default; migration 0036 seeds the active config's value instead.
    "manual_rate": 10,
    # Not documented: GetAccount reports SendQuota.MaxSendRate (_SES_GET_ACCOUNT). Migration 0036 seeds the
    # active config's max_send_rate here so Smart rate has a bound before ses:GetAccount is granted.
    "provider_limit": None,
    # _SES_QUOTAS, sandbox: "your maximum sending rate is one message per second".
    "fallback_rate": 1,
    # App default: the account's rate is shared with any other sender using it.
    "headroom": 0.9,
    "burst": 2,
    "recovery_interval_seconds": 60,
    "backoff_initial_seconds": 1,
    # _SES_QUOTA_ERRORS: wait before retrying a quota error; AWS suggests up to 10 minutes.
    "backoff_max_seconds": 600,
    # Not documented: GetAccount reports SendQuota.Max24HourSend (-1 = no limit).
    "daily_limit": None,
    "budget_headroom": 1.0,
    "transactional_reserve": None,
    # App default: how often Smart rate re-reads GetAccount...
    "discovery_interval_seconds": 3_600,
    # ...and when it probes again after "Daily message quota exceeded" (SES drops the message, so it is safe).
    "quota_recheck_seconds": 600,
    # App default: connect and read timeout of each SendRawEmail call (botocore's own default is 60 s). SES answers
    # in well under a second, and sign-in codes are sent inside a request, so this stays below
    # waits.inline_request_budget_seconds.
    "request_timeout_seconds": 10,
}

SMTP_SEND = {
    "smart_enabled": True,
    # App default; migration 0036 seeds max_send_rate × 60 instead while SMTP is the active provider.
    "manual_rate": 30,
    # Not documented in general; the host profiles below cover Google's SMTP servers.
    "provider_limit": None,
    # App default (labelled "limit unknown" in the admin): SMTP servers report no rate.
    "fallback_rate": 60,
    "headroom": 0.9,
    # One connection and login per message, so no back-to-back sends.
    "burst": 1,
    "recovery_interval_seconds": 600,
    "backoff_initial_seconds": 30,
    "backoff_max_seconds": 900,
    "daily_limit": None,
    "daily_message_limit": None,
    "budget_headroom": 1.0,
    "transactional_reserve": None,
    # Documented daily limits of known SMTP hosts, used while the policy's own field is blank.
    "host_profiles": {
        # _GMAIL_SMTP: "The sending limit is 2,000 messages per day".
        "smtp.gmail.com": {"daily_message_limit": 2_000},
        # _GMAIL_RELAY: "Each user can send up to 10,000 messages in a 24-hour period" and to at most "10,000
        # unique recipients in a 24-hour period".
        "smtp-relay.gmail.com": {"daily_message_limit": 10_000, "daily_limit": 10_000},
    },
    # App default: pause after Google's "454 4.7.0 Too many sign-in attempts" before logging in again.
    "sign_in_pause_seconds": 300,
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

GMAIL_API_SEND = {
    "smart_enabled": True,
    # App default: Google documents no per-minute sending rate.
    "manual_rate": 20,
    # _GMAIL_API_QUOTA: 6,000 quota units "Per minute per user per project" ÷ 100 units per messages.send. A project
    # that used the API before the 2026 quota change may have more; raise it with DELIVERY_RATES_OVERRIDES.
    "provider_limit": 60,
    "fallback_rate": None,
    # App default: the per-minute bound is derived, and "If a user exceeds their sending limits, their account
    # might be suspended" (_GMAIL_SENDING_LIMITS).
    "headroom": 0.5,
    "burst": 3,
    "recovery_interval_seconds": 600,
    # _GMAIL_API_ERRORS: "Start retry periods at least one second after the error."
    "backoff_initial_seconds": 1,
    "backoff_max_seconds": 60,
    # _GMAIL_SENDING_LIMITS, over a rolling 24 h: "Unique recipients per day" 3,000, of which 2,000 external, and
    # 2,000 messages per day. Every recipient is counted (not only unique ones), which is the conservative side.
    "daily_limit": 3_000,
    "daily_external_limit": 2_000,
    "daily_message_limit": 2_000,
    # Blank: every recipient counts as external. Google counts everything outside the Workspace primary domain.
    "internal_domain": "",
    # App default: Google may accept and then drop mail for minutes past a limit, and people sending from this
    # account in Gmail share the limits unseen, so the site stops at 90 % of each one.
    "budget_headroom": 0.9,
    # App default: hitting a daily limit blocks login codes for up to 24 hours, so campaigns leave 25 % for them.
    "transactional_reserve": 0.25,
    # App default: probe again after a "dailyLimitExceeded" (project quota)...
    "daily_quota_recheck_seconds": 3_600,
    # ...and after a bandwidth 429 (_GMAIL_API_ERRORS: limits "equal to, but independent of, IMAP")...
    "bandwidth_breaker_seconds": 3_600,
    # ...and pause this long after "Too many concurrent requests for user".
    "concurrent_throttle_seconds": 1,
}

SMS_SEND = {
    "smart_enabled": True,
    # App default, in messages per second.
    "manual_rate": 1,
    # _SMS_QUOTAS: SendTextMessage "1" request per second per account and Region (increase-eligible).
    "provider_limit": 1,
    "fallback_rate": None,
    "headroom": 1.0,
    "burst": 1,
    "recovery_interval_seconds": 60,
    "backoff_initial_seconds": 1,
    "backoff_max_seconds": 60,
    # Not documented in general: DescribePhoneNumbers reports the number's RateLimits (_SMS_MPS)...
    "parts_limit": None,
    # ...and until it has, Smart rate assumes one message part per second (a CA long code's MPS).
    "parts_fallback_rate": 1,
    "daily_limit": None,
    "budget_headroom": 1.0,
    "transactional_reserve": None,
    # App default: how often Smart rate re-reads the number's limits and the spend limit...
    "discovery_interval_seconds": 21_600,
    # ...and how often it probes after AWS reports the monthly spend limit reached.
    "spend_probe_seconds": 3_600,
    # App default: connect and read timeout of each SendTextMessage call (botocore's own default is 60 s); below
    # waits.inline_request_budget_seconds, as sign-in codes are sent inside a request.
    "request_timeout_seconds": 10,
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

"""
Signal patterns for ``DELIVERY_RATES["signals"]``: which provider answers mean "slow down", "pause", "a quota is
used up" or "blocked".

Each adapter (``apps.core.services.delivery_rates``) reads its own entry. Lists ending in ``_statuses`` hold HTTP
statuses or SMTP reply codes; every other list holds error codes, reasons or texts, matched case-insensitively
(texts as substrings). Free provider text is only matched against these lists, never stored or echoed.
"""

# Microsoft Graph sendMail, mailbox reads and the token endpoint.
# https://learn.microsoft.com/en-us/graph/throttling-limits and
# https://learn.microsoft.com/en-us/graph/errors (innermost error code).
GRAPH = {
    # 429 Too Many Requests; Outlook may also answer 503 or 509 when throttling (with Retry-After).
    "throttle_statuses": (429, 503, 509),
    "quota_codes": ("ErrorSubmissionQuotaExceeded",),
    # Pushback on a non-429 status: pause, and the message counts as possibly sent.
    "pause_codes": ("ApplicationThrottled", "ErrorExceededMessageLimit"),
    # Microsoft Entra token endpoint: busy, or too many requests for this app.
    # Any other token failure (invalid_client, an unknown AADSTS code, ...) stops Graph until the config is saved.
    "token_pause_codes": ("temporarily_unavailable", "AADSTS50196", "AADSTS90055"),
    # 507 Insufficient Storage: the sender mailbox is full.
    "mailbox_full_statuses": (507,),
}

# Amazon SES SendRawEmail (v1 API).
# https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas-errors.html
SES = {
    "throttle_codes": ("Throttling", "ThrottlingException"),
    "throttle_texts": ("Maximum sending rate exceeded",),
    # "Amazon SES drops the message and doesn't attempt to redeliver it", so a retry later is safe.
    "quota_texts": ("Daily message quota exceeded",),
    "blocked_codes": ("AccountSendingPausedException",),
    # Pauses only the configuration set campaigns use.
    "bulk_blocked_codes": ("ConfigurationSetSendingPausedException",),
    # About this one message, not the rate.
    "message_codes": ("MessageRejected",),
}

# SMTP, including Gmail SMTP and the Workspace SMTP relay. Google reuses reply codes, so texts are matched against
# "<code> <enhanced status> <text>".
# https://knowledge.workspace.google.com/admin/gmail/advanced/smtp-relay-service-error-messages and
# https://knowledge.workspace.google.com/admin/support/troubleshooting/gmail-smtp-errors-and-codes
SMTP = {
    # "421 4.7.0 Try again later", "450 4.2.1 Peak SMTP relay limit exceeded", SES SMTP "454 Throttling failure".
    "throttle_texts": ("421 4.7.0", "Peak SMTP relay limit", "Maximum sending rate exceeded"),
    # "454 4.7.0 Too many sign-in attempts": pause for channels.smtp_send.sign_in_pause_seconds.
    "pause_texts": ("Too many sign-in attempts",),
    # "550 5.4.5 Daily user sending limit exceeded", "550 5.7.1 Daily SMTP relay sending limit exceeded",
    # SES SMTP "454 Throttling failure: Daily message quota exceeded".
    "quota_texts": ("550 5.4.5", "Daily SMTP relay sending limit exceeded", "Daily message quota exceeded"),
    # One recipient receiving too fast ("450 4.2.1" / "550 5.2.1"), or too many recipients ("452 4.5.3"): about
    # this message only.
    "message_texts": (
        "receiving mail too quickly",
        "receiving email too quickly",
        "receiving mail at a rate",
        "452 4.5.3",
    ),
    # 534 / 535: authentication refused.
    "auth_blocked_statuses": (534, 535),
}

# Gmail IMAP (admin inbox and "Import from Gmail").
# https://support.google.com/mail/answer/7126229 and
# https://knowledge.workspace.google.com/admin/gmail/gmail-bandwidth-limits
IMAP = {
    # Pause for channels.gmail_imap.connections_pause_seconds.
    "pause_texts": ("Too many simultaneous connections",),
    # Suspension for channels.gmail_imap.bandwidth_breaker_seconds.
    "bandwidth_texts": ("[OVERQUOTA]", "Account exceeded command or bandwidth limits"),
    "throttle_texts": ("[UNAVAILABLE]", "[THROTTLED]"),
    "auth_blocked_texts": ("AUTHENTICATIONFAILED", "Application-specific password required"),
}

# Gmail API messages.send and the Google token endpoint.
# https://developers.google.com/workspace/gmail/api/guides/handle-errors and
# https://developers.google.com/identity/protocols/oauth2/service-account
GMAIL_API = {
    # 403 usageLimits reasons (legacy camelCase and ErrorInfo UPPER_SNAKE): back off and retry.
    "throttle_reasons": ("rateLimitExceeded", "userRateLimitExceeded", "RATE_LIMIT_EXCEEDED"),
    # 403 dailyLimitExceeded: the project's quota is used up; probe again after
    # channels.gmail_api_send.daily_quota_recheck_seconds.
    "daily_quota_reasons": ("dailyLimitExceeded",),
    "blocked_reasons": ("domainPolicy", "failedPrecondition", "FAILED_PRECONDITION"),
    # About this one message.
    "message_reasons": ("badRequest", "invalidArgument", "INVALID_ARGUMENT"),
    # 429 texts: "User-rate limit exceeded (Mail sending)" is the daily sending limit (breaker, up to 24 hours);
    # "Too many concurrent requests for user" a short throttle; "User-rate limit exceeded" alone the bandwidth limit.
    "mail_sending_texts": ("(Mail sending)",),
    "concurrent_texts": ("concurrent requests",),
    "bandwidth_texts": ("User-rate limit exceeded",),
    "throttle_statuses": (408, 429),
    # Token endpoint: retryable codes (a token request sends no mail)...
    "token_pause_codes": ("temporarily_unavailable", "server_error", "internal_failure"),
    # ...and codes that block until the delegation, key or service account is fixed.
    "token_blocked_codes": (
        "unauthorized_client",
        "access_denied",
        "admin_policy_enforced",
        "invalid_grant",
        "disabled_client",
        "invalid_client",
        "deleted_client",
        "org_internal",
        "invalid_scope",
    ),
}

# AWS End User Messaging SMS SendTextMessage (pinpoint-sms-voice-v2); reasons are the top-level ``Reason``.
# https://docs.aws.amazon.com/pinpoint/latest/apireference_smsvoicev2/CommonErrors.html
SMS = {
    "throttle_codes": ("ThrottlingException",),
    # ServiceQuotaExceededException with this reason: probe every channels.sms_send.spend_probe_seconds.
    "spend_reasons": ("MONTHLY_SPEND_LIMIT_REACHED_FOR_TEXT",),
    # AccessDeniedException: the account cannot send (the breaker's timed probe re-checks)...
    "blocked_reasons": ("ACCOUNT_DISABLED", "INSUFFICIENT_ACCOUNT_REPUTATION"),
    # ...and ConflictException: no usable origination identity, which saving the AWS configuration may fix.
    "config_blocked_reasons": ("NO_ORIGINATION_IDENTITIES_FOUND",),
    # About this one message or number.
    "message_codes": ("ValidationException",),
    "message_reasons": ("DESTINATION_PHONE_NUMBER_OPTED_OUT",),
}

SIGNALS = {
    "graph": GRAPH,
    "ses": SES,
    "smtp": SMTP,
    "imap": IMAP,
    "gmail_api": GMAIL_API,
    "sms": SMS,
}

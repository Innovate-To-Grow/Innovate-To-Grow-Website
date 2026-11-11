import re

SENSITIVE_FIELD_RE = re.compile(
    r"(password|secret|token|api[_-]?key|private|credential|session|hash|salt)",
    re.IGNORECASE,
)
DENIED_FIELD_NAMES = {
    "is_staff",
    "is_superuser",
    "groups",
    "user_permissions",
    "permissions",
    "bypass_password",
}
DENIED_READ_APP_LABELS = {"admin", "contenttypes", "sessions"}
DENIED_WRITE_APP_LABELS = DENIED_READ_APP_LABELS | {"auth"}
DENIED_MODEL_LABELS = {
    "auth.group",
    "auth.permission",
    "core.awscredentialconfig",
    # Delivery-rate policy, live pacing state and usage: changing them would let a caller raise a rate or reopen a
    # provider breaker outside Mail → Delivery Rates. None of their names matches DENIED_MODEL_NAME_PARTS.
    "core.deliveryratelimit",
    "core.deliveryratepolicy",
    "core.deliveryratestate",
    "core.deliveryusagebucket",
    "core.emailserviceconfig",
    # Email telemetry and bounce processing: written only by the delivery facade and the bounce processor. A write
    # would falsify the delivery record or move the bounce scan's checkpoint; staff read them on the Email
    # Monitoring dashboard. None of their names matches DENIED_MODEL_NAME_PARTS.
    "core.emailbounce",
    "core.emailmonitorstate",
    "core.outboundemail",
    "core.outboundemailattempt",
    # Request limits: changing a policy, a Smart factor or the process heartbeats would loosen or tighten every
    # caller's limits outside the admin's audited page. None of their names matches DENIED_MODEL_NAME_PARTS.
    "core.requestlimitprocess",
    "core.requestratelimitpolicy",
    "core.requestratelimitstate",
    "core.gmailaccessaccount",
    # The Gmail API service account and its impersonation allow-list (the subject list matches no name part).
    "core.gmailapiproviderconfig",
    "core.gmailapisubject",
    "core.googlecredentialconfig",
    "core.microsoftgraphaccesscheck",
    "core.microsoftgraphcertificate",
    "core.microsoftgraphmailboxscope",
    "core.microsoftgraphproviderconfig",
    # Bounced addresses: staff review decisions, the bulk-mail suppression list and their audit log, written only by
    # Mail → Email Monitoring → Bounced addresses (a write would lift or set a suppression outside its guards).
    "mail.bounceaggregationstate",
    "mail.bouncedaddress",
    "mail.bouncedaddressaction",
    "mail.bouncedaddresscampaign",
    # SMS policy: the opt-out list (a write would text a number that replied STOP, or stop texting one), its sync
    # state, and the ticket-text log, written only by Mail → SMS Settings / SMS Opt-outs and the senders. SMS links
    # and SMS settings match "token" / "config" in DENIED_MODEL_NAME_PARTS.
    "mail.smsoptout",
    "mail.smsoptoutsyncstate",
    "mail.ticketsms",
    "system_intelligence.chatconversation",
    "system_intelligence.chatmessage",
    "system_intelligence.systemintelligenceactionrequest",
    "system_intelligence.systemintelligenceconfig",
    "cms.cmsblock",
    "cms.cmspage",
}
DENIED_MODEL_NAME_PARTS = ("credential", "config", "permission", "session", "logentry", "token")
SAFE_LOOKUPS = frozenset(
    {
        "exact",
        "iexact",
        "contains",
        "icontains",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
        "startswith",
        "istartswith",
        "endswith",
        "iendswith",
        "range",
        "date",
        "year",
        "month",
        "day",
        "isnull",
    }
)

__all__ = [
    "DENIED_FIELD_NAMES",
    "DENIED_MODEL_LABELS",
    "DENIED_MODEL_NAME_PARTS",
    "DENIED_READ_APP_LABELS",
    "DENIED_WRITE_APP_LABELS",
    "SAFE_LOOKUPS",
    "SENSITIVE_FIELD_RE",
]

# Most rows any record listing (assistant tool or CLI admin API) returns in one call.
MAX_ROWS = 50

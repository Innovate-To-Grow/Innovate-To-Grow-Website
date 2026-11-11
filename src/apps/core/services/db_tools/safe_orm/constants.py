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
    # The inbound mail queue (metadata of every message the mailbox scan lists) and the helpdesk built on it: mail
    # content, the people who wrote it and staff decisions on it. Staff work them in Helpdesk (its own app grant).
    "core.inboundmessage",
    "helpdesk.helpdesksettings",
    "helpdesk.ingestrecord",
    "helpdesk.ticket",
    "helpdesk.ticketattachment",
    "helpdesk.ticketcategory",
    "helpdesk.ticketevent",
    "helpdesk.ticketmessage",
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

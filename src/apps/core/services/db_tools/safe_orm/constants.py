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
    # Staged member imports: sheet values, member snapshots and the admin's pending choices, written only by the
    # Members → Import review and purged on a schedule. None of their names matches DENIED_MODEL_NAME_PARTS.
    "authn.memberimportbatch",
    "authn.memberimportrow",
    # The i2g-admin CLI's sign-in: the token exchange issues a bearer token for whichever member an authorization
    # code names, so a written code is a CLI session as anyone, the I2G Master included. The CLI denies both tables
    # for itself as well; the access tokens also match "token" in DENIED_MODEL_NAME_PARTS.
    "cli_admin.cliaccesstoken",
    "cli_admin.cliauthorizationcode",
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
    # The inbound mail queue (metadata of every message the helpdesk's intake lists) and the helpdesk built on it:
    # mail content, the people who wrote it, staff decisions on it, and the intake's checkpoint and lease (a write
    # would skip or re-import mail). Staff work them in Helpdesk (its own app grant).
    "core.inboundmessage",
    "helpdesk.helpdesksettings",
    "helpdesk.ingestrecord",
    "helpdesk.intakestate",
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
    # Bounced addresses: staff review decisions, the bulk-mail suppression list and their audit log, written only by
    # Mail → Email Monitoring → Bounced addresses (a write would lift or set a suppression outside its guards).
    "mail.bounceaggregationstate",
    "mail.bouncedaddress",
    "mail.bouncedaddressaction",
    "mail.bouncedaddresscampaign",
    # SMS policy: the opt-out list (a write would text a number that replied STOP, or stop texting one), its sync
    # state, the ticket-text log and the audit of personal sign-in link revocations, written only by Mail → SMS
    # Settings / SMS Opt-outs and the senders. SMS links and SMS settings match "token" / "config" in
    # DENIED_MODEL_NAME_PARTS.
    "mail.smslinkrevocation",
    "mail.smsoptout",
    "mail.smsoptoutsyncstate",
    "mail.ticketsms",
    "system_intelligence.chatconversation",
    "system_intelligence.chatmessage",
    "system_intelligence.systemintelligenceactionrequest",
    "system_intelligence.systemintelligenceconfig",
    # An admin's export belongs to them, like their conversations: its download authorizes on ``created_by``, so a
    # written owner hands one admin's file to another. The export tools create these rows themselves.
    "system_intelligence.systemintelligenceexport",
    "cms.cmsblock",
    "cms.cmspage",
}
DENIED_MODEL_NAME_PARTS = ("credential", "config", "permission", "session", "logentry", "token")
# Readable, never written by a proposed record write (nor are Django's auto-created many-to-many tables, such as
# Member.groups: see ``is_model_denied``). Contact rows are sign-in factors: a verified address or number signs in to
# its account, so they change only in the Members admin, under its owner guards and #732's code-only rule for phones.
# Verification challenges are the proof of a one-time code: a pending admin sign-in code re-pointed to another member
# signs in as them, and a phone challenge set to "verified" is a grant that event registration accepts. Accepting an
# admin invitation makes its address's member staff, so only the I2G Master writes invitations (in the admin). The
# active RSA key pair decrypts every password sign-in: a written public half breaks sign-in until a new key is made.
# The CLI audit log is the trail of every CLI write. Background jobs run whatever kind and payload a row names (a
# notification email to any address, a resent campaign or ticket), and retries go through the admin's Retry action
# and its guards; nothing in the assistant queues a job. The admin keeps the key, the audit log and the jobs read-only
# too. (The CLI denies all of authn.)
DENIED_WRITE_MODEL_LABELS = frozenset(
    {
        "authn.admininvitation",
        "authn.contactemail",
        "authn.contactphone",
        "authn.emailauthchallenge",
        "authn.phoneverificationchallenge",
        "authn.rsakeypair",
        "cli_admin.cliauditlog",
        "core.backgroundjob",
    }
)
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
    "DENIED_WRITE_MODEL_LABELS",
    "SAFE_LOOKUPS",
    "SENSITIVE_FIELD_RE",
]

# Most rows any record listing (assistant tool or CLI admin API) returns in one call.
MAX_ROWS = 50

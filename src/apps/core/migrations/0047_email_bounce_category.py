"""Bounce categories: what went wrong with each bounce report, from its SMTP reply code and enhanced status code (and,
for generic codes only, its diagnostic text), and its coarse classification derived from that.

Adds ``EmailBounce.category`` and ``EmailBounce.smtp_code`` (with database defaults, so the release before this one
can keep saving reports while a deploy rolls out; a report saved that way has an empty category and is classified when
the bounced addresses are next counted), redefines ``is_permanent`` as "the address itself will not work", and
classifies every stored report again from its stored action, status code and diagnostic: category, SMTP code,
classification, ``is_permanent`` and reason. Each matched email's worst classification is set again from its reports.

The classifier below is a frozen copy of ``apps.core.services.email.bounces.classify`` and its ``rules`` as of this
migration, so the migration keeps working when those change. The reverse keeps the new classifications (they are
valid values for the previous release) and drops the two columns.
"""

import re

from django.db import migrations, models

STATUS_RE = re.compile(r"(?<![\d.])([245])\.(\d{1,3})\.(\d{1,3})(?![\d.])")
SMTP_START_RE = re.compile(r"^\s*([245]\d\d)(?![\d.])")
SMTP_PAIR_RE = re.compile(r"(?<![\d.])([245]\d\d)[ -]+[245]\.\d{1,3}\.\d{1,3}(?![\d.])")
COARSE = {
    "hard": "hard",
    "mailbox_disabled": "hard",
    "mailbox_full": "soft",
    "transient": "soft",
    "spam_rejected": "rejected",
    "relay_denied": "rejected",
    "policy_rejected": "rejected",
    "delayed": "delayed",
    "unknown": "unknown",
}
ADDRESS_FAILS = {"hard": True, "mailbox_disabled": True, "unknown": None}
DEFAULT_REASONS = {
    "hard": "Recipient address does not exist",
    "mailbox_disabled": "Recipient mailbox is disabled",
    "mailbox_full": "Recipient mailbox is full",
    "transient": "Temporary failure",
    "spam_rejected": "Rejected as spam, or for our sending reputation or authentication",
    "relay_denied": "Relay denied",
    "policy_rejected": "Rejected by the recipient's server policy",
    "unknown": "Delivery failed; the report does not say why",
}
EXACT = {
    "5.1.7": "spam_rejected",
    "5.1.8": "spam_rejected",
    "5.1.90": "transient",
    "5.2.1": "mailbox_disabled",
    "5.2.2": "mailbox_full",
    "4.2.2": "mailbox_full",
    "5.2.3": "transient",
    "5.2.4": "transient",
    "5.2.121": "transient",
    "5.2.122": "transient",
    "5.3.4": "transient",
    "5.4.1": "hard",
    "5.4.4": "hard",
    "5.4.310": "hard",
    "5.7.9": "spam_rejected",
    "5.7.350": "spam_rejected",
    "5.7.511": "spam_rejected",
    "5.7.513": "spam_rejected",
    "5.7.750": "spam_rejected",
    "5.7.54": "relay_denied",
    "5.7.57": "relay_denied",
    "5.7.60": "relay_denied",
    "5.7.64": "relay_denied",
}
RANGES = (
    (5, 7, 20, 29, "spam_rejected"),
    (4, 7, 20, 29, "spam_rejected"),
    (5, 7, 501, 503, "spam_rejected"),
    (5, 7, 506, 509, "spam_rejected"),
    (5, 7, 606, 649, "spam_rejected"),
    (5, 7, 700, 749, "spam_rejected"),
)
SUBJECT_DEFAULTS = {
    0: "unknown",
    2: "unknown",
    3: "transient",
    4: "transient",
    5: "unknown",
    6: "transient",
    7: "policy_rejected",
}
ADDRESS_DETAILS = frozenset({0, 1, 2, 3, 4, 6, 10})
AMBIGUOUS = frozenset({"5.4.1", "5.4.4"})
SIZE_CODES = frozenset({"5.2.3", "5.3.4"})
REASONS = {
    "5.1.0": "Bad recipient address",
    "5.1.1": "Recipient mailbox does not exist",
    "5.1.2": "Recipient domain does not exist",
    "5.1.3": "Invalid recipient address",
    "5.1.6": "Recipient mailbox has moved",
    "5.1.7": "Rejected: our sender address was refused",
    "5.1.8": "Rejected: our sender domain or sending mailbox was refused",
    "5.1.10": "Recipient not found",
    "5.1.90": "Our mailbox reached its daily recipient limit",
    "5.2.1": "Recipient mailbox is disabled",
    "5.2.2": "Recipient mailbox is full",
    "4.2.2": "Recipient mailbox is full",
    "5.2.3": "Message too large for the recipient",
    "5.3.4": "Message too large",
    "5.4.1": "Recipient address rejected (access denied)",
    "5.4.4": "Recipient domain has no mail server",
    "5.4.6": "Mail routing loop",
    "5.4.7": "Delivery expired",
    "5.4.14": "Mail routing loop (hop count exceeded)",
    "5.4.300": "Delivery expired",
    "5.4.310": "Recipient domain does not exist",
    "5.4.312": "Delivery expired: DNS lookup failed",
    "5.4.316": "Delivery expired: connection refused",
    "4.4.7": "Delivery expired",
    "5.7.1": "Rejected by the recipient's server policy",
    "5.7.9": "Rejected: not accepted for policy reasons (content or sending reputation)",
    "5.7.12": "Rejected: the recipient takes mail only from authenticated or internal senders",
    "5.7.23": "Rejected: sender authentication (SPF) failed",
    "5.7.25": "Rejected: reverse DNS check of our server failed",
    "5.7.26": "Rejected: sender authentication (DMARC) failed",
    "5.7.54": "Relay denied: unable to relay",
    "5.7.57": "Relay denied: our client was not authenticated",
    "5.7.64": "Relay denied: tenant attribution",
    "5.7.350": "Rejected as spam by the remote server",
    "5.7.509": "Rejected: sender authentication (DMARC) failed",
    "5.7.606": "Rejected: sending server is blocked",
    "5.7.708": "Rejected: sending server is not trusted",
}
SUBJECT_REASONS = {
    "1": "Recipient address problem",
    "2": "Recipient mailbox problem",
    "3": "Recipient mail system problem",
    "4": "Network or routing problem",
    "5": "Mail protocol problem",
    "6": "Message content problem",
    "7": "Rejected by security or policy",
}
ZERO_LIMIT_RE = re.compile(
    r"\b(?:max(?:imum)?|limit|allowed)\b[^0-9.;]{0,40}?(?<![\d.])0(?:\.0+)? ?(?:[kmg]i?b|bytes?|"
    r"k)\b"
)
ZERO_LIMIT_REASON = "Recipient mailbox accepts no messages (0 KB size limit): treated as disabled"
# (category, reason, pattern), in order; the first match wins.
PHRASES = (
    (
        "relay_denied",
        "Relay denied: the receiving server would not take our message by this route",
        re.compile(
            r"\brelay(?:ing)? (?:access )?(?:is )?(?:denied|refused|prohibited|not (?:permitted|allowed))|"
            r"\b(?:unable|not (?:permitted|allowed)|cannot|can't) (?:to )?relay\b|\bwe do not relay\b|"
            r"\btenantattribution\b|\ballowed rcpthosts\b"
        ),
    ),
    (
        "spam_rejected",
        "Rejected as spam, or for our sending reputation or authentication",
        re.compile(
            r"spam|unsolicited|\b(?:junk|bulk) e?-?mail\b|\bphish|\bvirus|\bmalware|\bsuspicious\b|\b(?:block|"
            r"black|deny) ?-?list|\b(?:rbl|dnsbl|surbl|ipcheck)\b|reputation|content filter|\bbanned\b|"
            r"\bblocked using\b|\bpolicy reasons\b|\b(?:tss0\d|ts0\d|ph01|bl2\d)\b|\b(?:dmarc|spf|dkim)\b|"
            r"\bunauthenticated\b|\bauthentication (?:fail|check)|\breverse dns\b|\bptr record|\brdns\b|"
            r"\bcannot find your (?:reverse )?hostname\b|\bsender (?:address|domain)\b[^.;]{0,30}?\b(?:rejected|"
            r"refused|invalid|not found|does not exist)\b"
        ),
    ),
    (
        "mailbox_disabled",
        "Recipient mailbox is disabled",
        re.compile(
            r"(?<!sender )(?<!sending )(?<!your )\b(?:account|mailbox|user|recipient|inbox)\b[^.;:]{0,40}?\b(?:is|"
            r"has been|was) (?:disabled|deactivated|suspended|inactive|closed)\b|"
            r"(?<!sender )(?<!your )\b(?:account|mailbox|user|inbox) (?:disabled|deactivated|suspended|"
            r"inactive)\b|\b(?:disabled|deactivated|suspended|inactive) (?:account|mailbox|user|inbox)\b|"
            r"\b554\.30\b"
        ),
    ),
    (
        "hard",
        "Recipient address does not exist",
        re.compile(
            r"\buser unknown\b|\bunknown (?:user|recipient|mailbox|addressee)\b|\baddressee unknown\b|"
            r"\bno such (?:user|mailbox|recipient|address|account|person)\b|\bno mailbox (?:here|by that name)\b|"
            r"\b(?:recipient|address|mailbox|account|user)\b[^.;:]{0,40}?\b(?:does not|doesn't|did not) exist\b|"
            r"\bdoes(?:n't| not) have an? [\w.-]{1,40} account\b|\brecipient (?:not found|unknown|invalid)\b|"
            r"\brecipientnotfound\b|\binvalid (?:recipient|mailbox)\b|\bmailbox (?:not found|unknown)\b|"
            r"\baddress (?:not found|(?:could ?n[o']t|cannot|can't) be found)\b|\bunrout(?:e)?able address\b|"
            r"\bnot a valid (?:user|recipient|mailbox)\b|\bnxdomain\b|\bnon-?existent (?:domain|user|mailbox|"
            r"address|recipient)\b|\bhost (?:or domain name )?not found\b(?!,? try again)|"
            r"\bdomain (?:name )?(?:not found|does not exist)\b"
        ),
    ),
    (
        "mailbox_full",
        "Recipient mailbox is full",
        re.compile(
            r"\b(?:mailbox|mail box|inbox|account|disk|user|recipient)\b[^.;:]{0,20}?\b(?:is )?full\b|"
            r"\bover ?quota\b|\bquota (?:exceeded|full|reached)\b|\bexceed(?:s|ed)? (?:the |its )?(?:storage|"
            r"quota)\b|\bout of storage\b|\binsufficient (?:storage|disk space)\b|"
            r"\bstorage (?:allocation )?exceeded\b|\bexceeded storage allocation\b|"
            r"\bmailbox (?:size )?limit exceeded\b"
        ),
    ),
    (
        "transient",
        "Message too large",
        re.compile(
            r"\btoo (?:large|big)\b|\bsize ?limit|\bmessage (?:size|length)\b|\bmax(?:imum)? (?:message |"
            r"receive )?size\b"
        ),
    ),
    (
        "transient",
        "Connection timed out",
        re.compile(r"\btimed? ?-?out\b|\b(?:winsock|socket) error code:? ?10060\b"),
    ),
    (
        "transient",
        "Could not connect to the recipient's mail server",
        re.compile(
            r"\bconnection (?:refused|reset|dropped|closed|lost|failed|attempt failed)\b|\bno route to host\b|"
            r"\b(?:could not|couldn't|unable to|failed to|cannot|can't) (?:establish (?:a )?)?connect(?:ion)?\b|"
            r"\b(?:network|host) (?:is )?unreachable\b|\b(?:winsock|socket) error\b"
        ),
    ),
    (
        "transient",
        "DNS lookup failed",
        re.compile(r"\bdns\b[^.;:]{0,30}?\b(?:fail(?:ed|ure)?|error|timeout|problem)\b|\bservfail\b"),
    ),
    (
        "transient",
        "Delivery expired after retries",
        re.compile(r"\bexpired\b|\bgiving up\b|\bgave up\b"),
    ),
    (
        "transient",
        "Mail routing loop",
        re.compile(r"\bmail loop\b|\bloop(?:ing)? detected\b|\bhop count\b|\btoo many hops\b"),
    ),
    (
        "transient",
        "Temporary failure: the server asked to try again later",
        re.compile(
            r"\b(?:try|come back|retry)(?: again)? later\b|\btry again\b|\btemporar(?:y|ily)\b|\bdeferr?(?:ed|"
            r"al)\b|\bgr[ae]y ?-?list|\brate ?-?limit|\bthrottl|\btoo many (?:connections|messages|recipients|"
            r"concurrent|sessions)\b|\bserver (?:is )?busy\b|\bservice (?:is )?(?:temporarily |"
            r"currently )?(?:not available|unavailable)\b|\binsufficient system (?:storage|resources)\b"
        ),
    ),
    (
        "policy_rejected",
        "Rejected by the recipient's server policy",
        re.compile(
            r"\bpolic(?:y|ies)\b|\bnot (?:authori[sz]ed|permitted|allowed)\b|\baccess denied\b|\bprohibited\b|"
            r"\bsender (?:is )?(?:denied|blocked)\b|\bblocked sender\b|\brestrict(?:ed|ion)\b|\bmoderat(?:ed|ion|"
            r"or)\b|\bauthentication required\b|\bauthrequired\b|\bnotauthorized\b|\bonly (?:accepts?|"
            r"receives?)\b|\brejected by (?:the )?(?:recipient|administrator|organi[sz]ation|transport rule)\b"
        ),
    ),
)
SIZE_INDEX = 5
ALL = frozenset(
    {
        "delayed",
        "hard",
        "mailbox_disabled",
        "mailbox_full",
        "policy_rejected",
        "relay_denied",
        "spam_rejected",
        "transient",
        "unknown",
    }
)
TEMPORARY_REFINEMENTS = frozenset({"mailbox_full", "relay_denied", "spam_rejected"})
POLICY_REFINEMENTS = frozenset({"hard", "mailbox_disabled", "policy_rejected", "relay_denied", "spam_rejected"})
AMBIGUOUS_REFINEMENTS = frozenset({"transient"})
NOT_FAILURES = frozenset({"delivered", "expanded", "relayed"})
SEVERITY = {"hard": 4, "rejected": 3, "soft": 2, "unknown": 1, "delayed": 0}
SPACE_RE = re.compile(r"\s+")
TEXT_LIMIT = 1000


def reason(status):
    if status in REASONS:
        return REASONS[status]
    parts = status.split(".")
    if len(parts) != 3:
        return ""
    base = SUBJECT_REASONS.get(parts[1], "Delivery failure")
    return f"Temporary: {base.lower()}" if parts[0] == "4" else base


def specific(klass, subject, detail):
    code = f"{klass}.{subject}.{detail}"
    if code in EXACT:
        return EXACT[code]
    for range_class, range_subject, low, high, category in RANGES:
        if (klass, subject) == (range_class, range_subject) and low <= detail <= high:
            return category
    return None


def default(klass, subject, detail):
    if klass == 4:
        return "transient"
    if subject == 1:
        return "hard" if detail in ADDRESS_DETAILS else "unknown"
    return SUBJECT_DEFAULTS.get(subject, "unknown")


def is_generic(klass, subject, detail):
    if specific(klass, subject, detail) is not None:
        return False
    if subject == 0 or detail == 0:
        return True
    return (klass, subject) in ((5, 5), (4, 7)) or (klass, subject, detail) == (5, 7, 1)


def refine(text, allowed):
    """``(category, reason)`` of the first phrase in ``text`` whose category is allowed, or None."""
    for index, (category, why, pattern) in enumerate(PHRASES):
        if category in allowed and pattern.search(text):
            if index == SIZE_INDEX and "mailbox_disabled" in allowed and ZERO_LIMIT_RE.search(text):
                return "mailbox_disabled", ZERO_LIMIT_REASON
            return category, why
    return None


def smtp_code(diagnostic):
    text = str(diagnostic or "")[:TEXT_LIMIT]
    match = SMTP_START_RE.match(text) or SMTP_PAIR_RE.search(text)
    return match.group(1) if match else ""


def parts_of(code):
    pieces = str(code or "").split(".")
    if len(pieces) != 3 or not all(piece.isdigit() for piece in pieces):
        return None
    return int(pieces[0]), int(pieces[1]), int(pieces[2])


def effective_status(status, diagnostic):
    parts = parts_of(status)
    if parts is not None and not is_generic(*parts):
        return status
    for match in STATUS_RE.finditer(str(diagnostic or "")[:TEXT_LIMIT]):
        found = parts_of(".".join(match.groups()))
        if found[0] in (4, 5) and (parts is None or found[0] == parts[0]) and not is_generic(*found):
            return ".".join(match.groups())
    return status


def refined(text, allowed, fallback):
    found = refine(text, allowed)
    return found if found is not None else (fallback, "")


def decide(status, smtp, text):
    parts = parts_of(status)
    if parts is None:
        if smtp.startswith("4"):
            return refined(text, TEMPORARY_REFINEMENTS, "transient")
        return refined(text, ALL, "unknown")
    if status in SIZE_CODES and ZERO_LIMIT_RE.search(text):
        return "mailbox_disabled", ZERO_LIMIT_REASON
    found = specific(*parts)
    if status in AMBIGUOUS:
        return refined(text, AMBIGUOUS_REFINEMENTS, found)
    if found is not None:
        return found, ""
    category = default(*parts)
    if not is_generic(*parts):
        return category, ""
    if parts[0] == 4:
        return refined(text, TEMPORARY_REFINEMENTS, category)
    return refined(text, POLICY_REFINEMENTS if parts[1] == 7 else ALL, category)


def reason_for(status, text, category):
    if status in REASONS:
        return REASONS[status]
    found = refine(text, {category})
    if found is not None:
        return found[1]
    parts = parts_of(status)
    if parts is None or is_generic(*parts) or specific(*parts) is not None:
        return DEFAULT_REASONS[category]
    return reason(status)


def categorize(status, smtp, text):
    if not (status or smtp or text):
        return "unknown", "The report gives no status code"
    category, why = decide(status, smtp, text)
    return category, why or reason_for(status, text, category)


def classify(action, status, diagnostic):
    """``(classification, category, is_permanent, reason, smtp_code)``, or None when the message went through."""
    action = str(action or "").strip().lower()
    status = str(status or "")
    if action in NOT_FAILURES or status.startswith("2."):
        return None
    diagnostic = str(diagnostic or "")[:TEXT_LIMIT]
    smtp = smtp_code(diagnostic)
    if action == "delayed":
        return "delayed", "delayed", False, reason(status) or "Delivery delayed; the server keeps retrying", smtp
    category, why = categorize(effective_status(status, diagnostic), smtp, SPACE_RE.sub(" ", diagnostic).lower())
    return COARSE[category], category, ADDRESS_FAILS.get(category, False), why, smtp


FIELDS = ("classification", "category", "is_permanent", "reason", "smtp_code")
# A stored report is always a failure or a delay; should one ever read as delivered, it is kept as unknown.
NO_VERDICT = ("unknown", "unknown", None, "The report gives no status code", "")


def classify_stored_reports(apps, schema_editor):
    EmailBounce = apps.get_model("core", "EmailBounce")
    OutboundEmail = apps.get_model("core", "OutboundEmail")
    emails, last = set(), None
    while True:
        rows = EmailBounce.objects.order_by("pk").only("pk", "email_id", "action", "status_code", "diagnostic_code")
        batch = list((rows if last is None else rows.filter(pk__gt=last))[:500])
        if not batch:
            break
        for bounce in batch:
            verdict = classify(bounce.action, bounce.status_code, bounce.diagnostic_code) or NO_VERDICT
            for name, value in zip(FIELDS, verdict, strict=True):
                setattr(bounce, name, value[:255] if name == "reason" else value)
            if bounce.email_id is not None:
                emails.add(bounce.email_id)
        EmailBounce.objects.bulk_update(batch, FIELDS)
        last = batch[-1].pk
    for email_id in emails:
        kinds = EmailBounce.objects.filter(email_id=email_id).exclude(classification="delayed")
        worst = max(kinds.values_list("classification", flat=True), key=lambda kind: SEVERITY.get(kind, 0), default="")
        if worst:
            OutboundEmail.objects.filter(pk=email_id).update(bounce_classification=worst)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0046_inbound_message"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailbounce",
            name="category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("hard", "Address does not exist"),
                    ("mailbox_disabled", "Mailbox disabled"),
                    ("mailbox_full", "Mailbox full"),
                    ("transient", "Temporary failure"),
                    ("spam_rejected", "Spam or reputation rejection"),
                    ("relay_denied", "Relay denied"),
                    ("policy_rejected", "Recipient policy rejection"),
                    ("delayed", "Delayed (still retrying)"),
                    ("unknown", "Unknown failure"),
                ],
                db_default="",
                db_index=True,
                default="",
                help_text="What went wrong, from the SMTP reply code, the enhanced status code and (for generic codes "
                "only) the diagnostic text; the classification is derived from it. Empty: not classified yet (a report "
                "saved by the previous release during a deploy), classified when the bounced addresses are next "
                "counted.",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="emailbounce",
            name="smtp_code",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                help_text="The SMTP reply code (such as 550) of the diagnostic.",
                max_length=3,
            ),
        ),
        migrations.AlterField(
            model_name="emailbounce",
            name="is_permanent",
            field=models.BooleanField(
                blank=True,
                help_text="Whether the address itself will not work (address does not exist, mailbox disabled); "
                "empty when the report does not say.",
                null=True,
            ),
        ),
        migrations.RunPython(classify_stored_reports, migrations.RunPython.noop),
    ]

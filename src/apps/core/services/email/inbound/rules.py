"""The classifier's rule tables: which headers, senders, subjects and phrases mark mail as automated.

Only header-level signals (and the auto-reply subject prefixes, which mail systems write themselves) put a message
in an automated class; phrases in the text only choose the subtype of a message already known to be an automatic
reply, or add a hint to a human one. Everything is compared case-insensitively.
"""

import re

# The classes, from the site's own mail to a person's (``classify`` tries them in this order).
OWN, BOUNCE, RECEIPT, AUTO_REPLY, LEFT_ORG = "own", "bounce", "receipt", "auto_reply", "left_org"
SYSTEM, BULK, SPAM, HUMAN = "system", "bulk", "spam", "human"
AUTOMATED = frozenset({OWN, BOUNCE, RECEIPT, AUTO_REPLY, LEFT_ORG, SYSTEM, BULK, SPAM})
LABELS = {
    OWN: "Sent from the site's own address",
    BOUNCE: "Bounce or delay report",
    RECEIPT: "Read or delivery receipt",
    AUTO_REPLY: "Automatic reply",
    LEFT_ORG: "Left the organisation / address changed",
    SYSTEM: "Other system mail",
    BULK: "List or bulk mail",
    SPAM: "Spam",
    HUMAN: "Human (or uncertain)",
}

# Exchange, Gmail, Outlook.com and other systems' automatic-reply subject prefixes, in several languages.
AUTO_REPLY_SUBJECT_RE = re.compile(
    r"^\s*(?:automatic reply|auto[ -]?reply|auto[ -]?response|"
    r"out of (?:the )?office(?: reply| autoreply)?|abwesenheitsnotiz|automatische antwort|"
    r"r[ée]ponse automatique|respuesta autom[áa]tica|fuera de la oficina|risposta automatica|"
    r"resposta autom[áa]tica|automatisch antwoord|afwezig|autosvar|automaattinen vastaus|"
    r"automatick[áa] odpov[ěe]ď|odpowied[źz] automatyczna|otomatik yan[ıi]t|автоматический ответ|"
    r"自动回复|自動回覆|自動応答|자동 회신)\s*[:：]",
    re.IGNORECASE,
)
# Subjects that are only a hint on their own (a person may write them too).
AUTO_REPLY_HINT_RE = re.compile(r"\b(?:out of (?:the )?office|on vacation|on leave|away from (?:my|the) )", re.I)
RECEIPT_SUBJECT_RE = re.compile(r"^\s*(?:read|not read|delivered|read receipt|lu|gelesen|le[íi]do)\s*:", re.I)
CALENDAR_SUBJECT_RE = re.compile(
    r"^\s*(?:accepted|declined|tentative|tentatively accepted|new time proposed|"
    r"angenommen|abgelehnt|mit vorbehalt|accept[ée]|refus[ée]|aceptado|rechazado)\s*:",
    re.IGNORECASE,
)

# Wording of automatic replies that say the address no longer reaches the person (the bounced-addresses evidence).
LEFT_ORG_RE = re.compile(
    r"\b(?:no longer (?:with|at|work(?:s|ing)? (?:at|for)|employed|in use|active|valid|monitored|being monitored|"
    r"available|checked)|has left|have left|left the (?:company|organi[sz]ation|university|firm)|"
    r"(?:is|are) not (?:being )?monitored|not monitored|new (?:e-?mail|email) address|"
    r"changed (?:my|his|her|their) (?:e-?mail|email)|please (?:update|use) (?:my|the) new|"
    r"(?:my|this) (?:e-?mail|email) (?:address )?(?:has changed|will be deactivated|is being retired))",
    re.IGNORECASE,
)
VACATION_RE = re.compile(
    r"\b(?:out of (?:the )?office|on (?:vacation|holiday|leave|annual leave|parental leave)|away from|"
    r"limited access to (?:my )?e-?mail|will (?:be )?(?:back|return)|return(?:ing)? on|until (?:mon|tue|wed|thu|"
    r"fri|sat|sun|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|currently (?:away|traveling|travelling))",
    re.IGNORECASE,
)
# Other systems' automatic acknowledgements, challenge-response and quarantine notices.
SYSTEM_TEXT_RE = re.compile(
    r"\b(?:this is an automated (?:message|response|reply|notification)|"
    r"(?:we|i) (?:have )?received your (?:message|request|e-?mail)|your (?:request|ticket|case) (?:#|number|id)|"
    r"(?:verify|confirm) (?:that )?you are (?:a )?human|held in quarantine|quarantined|"
    r"(?:message|messages) (?:have been|has been|were) (?:held|quarantined|blocked))",
    re.IGNORECASE,
)

REPORT_SENDERS = ("postmaster", "mailer-daemon", "mail-daemon", "maildaemon")
NOREPLY_RE = re.compile(
    r"^(?:no[-_.]?reply|do[-_.]?not[-_.]?reply|donotreply|notifications?|bounces?)(?:[-+._].*)?$", re.I
)
QUARANTINE_LOCAL_RE = re.compile(r"(?:quarantine|spam[-_.]?digest|postmaster-digest)", re.IGNORECASE)

# Headers an RFC 3834 automatic responder (or a vendor's) sets.
AUTO_REPLY_HEADERS = ("x-autoreply", "x-autorespond", "x-autoreply-from", "x-mail-autoreply")
# Mailing lists and bulk senders (RFC 2369/2919, and the large email service providers' own headers).
LIST_HEADERS = ("list-id", "list-unsubscribe", "list-post", "list-help", "list-owner")
ESP_HEADERS = (
    "x-mailchimp-id",
    "x-mc-user",
    "x-campaign",
    "x-campaignid",
    "x-sg-eid",
    "x-sg-id",
    "x-mailgun-sid",
    "x-mailgun-tag",
    "x-ses-outgoing",
    "x-sfmc-stack",
    "x-mkto-mailingid",
    "x-hubspot-email",
    "x-constantcontact",
    "x-csa-complaints",
    "x-pm-message-id",
    "x-mandrill-user",
)
BULK_PRECEDENCE = ("bulk", "list", "junk")

SCL_RE = re.compile(r"(?:^|;)\s*SCL\s*:\s*(-?\d+)", re.IGNORECASE)
SPAM_VERDICT_RE = re.compile(r"(?:^|;)\s*SFV\s*:\s*(?:SPM|SKS|SKB)\b", re.IGNORECASE)
AUTH_RESULT_RE = re.compile(r"\b(spf|dkim|dmarc|compauth)\s*=\s*([a-z]+)", re.IGNORECASE)
DKIM_PASS_DOMAIN_RE = re.compile(r"\bdkim\s*=\s*pass\b[^;]*?\bheader\.(?:d|i)\s*=\s*@?([A-Za-z0-9.-]+)", re.I)

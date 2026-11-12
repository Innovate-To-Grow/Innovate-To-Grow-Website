"""Enhanced status codes (RFC 3463, ``class.subject.detail``): which decide a category on their own (``EXACT``,
``RANGES``), which are generic enough for the diagnostic text to refine (``is_generic``), what any other code means
(``default``), and the reason shown for a code (``reason``)."""

from apps.core.models import EmailBounce

Category = EmailBounce.Category
HARD, DISABLED, FULL = Category.HARD, Category.MAILBOX_DISABLED, Category.MAILBOX_FULL
TRANSIENT, UNKNOWN = Category.TRANSIENT, Category.UNKNOWN
SPAM, RELAY, POLICY = Category.SPAM_REJECTED, Category.RELAY_DENIED, Category.POLICY_REJECTED

# Codes that decide on their own, where the subject's default does not fit (most are Exchange Online's own).
EXACT = {
    "5.1.7": SPAM,  # our sender address was refused
    "5.1.8": SPAM,  # our sender domain refused; Exchange: our mailbox is blocked for sending
    "5.1.90": TRANSIENT,  # Exchange: our mailbox reached its daily recipient limit
    "5.2.1": DISABLED,
    "5.2.2": FULL,
    "4.2.2": FULL,
    "5.2.3": TRANSIENT,  # message too large for the recipient (a 0 KB limit: see phrases.ZERO_LIMIT_RE)
    "5.2.4": TRANSIENT,
    "5.2.121": TRANSIENT,  # Exchange: the recipient's hourly receive limits
    "5.2.122": TRANSIENT,
    "5.3.4": TRANSIENT,  # message too large (a 0 KB limit: see phrases.ZERO_LIMIT_RE)
    "5.4.1": HARD,  # Exchange: "Recipient address rejected: Access denied" (no such recipient in the tenant)
    "5.4.4": HARD,  # unable to route: the domain takes no mail
    "5.4.310": HARD,  # Exchange: the DNS domain does not exist
    "5.7.9": SPAM,  # Yahoo: "Message not accepted for policy reasons" (content or sending reputation)
    "5.7.350": SPAM,  # Exchange: the remote server found spam
    "5.7.511": SPAM,  # Exchange: banned sender
    "5.7.513": SPAM,  # Exchange: our server is on the recipient's block list
    "5.7.750": SPAM,  # Exchange: unregistered sending domain
    "5.7.54": RELAY,  # Exchange: unable to relay
    "5.7.57": RELAY,  # Exchange: our client was not authenticated to send
    "5.7.60": RELAY,  # Exchange: no permission to send as this sender
    "5.7.64": RELAY,  # Exchange: TenantAttribution; relay access denied
}
# (class, subject, first detail, last detail, category)
RANGES = (
    (5, 7, 20, 29, SPAM),  # sender authentication: DKIM, SPF, reverse DNS, DMARC, null MX, mail flood, ARC
    (4, 7, 20, 29, SPAM),
    (5, 7, 501, 503, SPAM),  # Exchange: spam abuse detected, banned sender
    (5, 7, 506, 509, SPAM),  # Exchange: bad HELO, rejected by the recipient, our limits, DMARC
    (5, 7, 606, 649, SPAM),  # Exchange: banned sending IP
    (5, 7, 700, 749, SPAM),  # Exchange: our tenant blocked for sending spam
)
# What any other permanent code means, by subject. An address code (X.1.Y) is a missing address only for the details
# defined for one (RFC 3463, and X.1.10: null MX, Exchange's RecipientNotFound); any other bare code is unknown.
SUBJECT_DEFAULTS = {0: UNKNOWN, 2: UNKNOWN, 3: TRANSIENT, 4: TRANSIENT, 5: UNKNOWN, 6: TRANSIENT, 7: POLICY}
ADDRESS_DETAILS = frozenset({0, 1, 2, 3, 4, 6, 10})
# Codes servers use for more than one thing: a phrase may only make them temporary.
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


def reason(status: str) -> str:
    """The reason shown for a code: its own, else its subject's ("Temporary: ..." for a 4.x.x), or ""."""
    if status in REASONS:
        return REASONS[status]
    parts = status.split(".")
    if len(parts) != 3:
        return ""
    base = SUBJECT_REASONS.get(parts[1], "Delivery failure")
    return f"Temporary: {base.lower()}" if parts[0] == "4" else base


def specific(klass: int, subject: int, detail: int) -> str | None:
    """The category a code decides on its own, or None."""
    code = f"{klass}.{subject}.{detail}"
    if code in EXACT:
        return EXACT[code]
    for range_class, range_subject, low, high, category in RANGES:
        if (klass, subject) == (range_class, range_subject) and low <= detail <= high:
            return category
    return None


def default(klass: int, subject: int, detail: int) -> str:
    """The category of a code that nothing more specific names (and no phrase refined)."""
    if klass == 4:
        return TRANSIENT
    if subject == 1:
        return HARD if detail in ADDRESS_DETAILS else UNKNOWN
    return SUBJECT_DEFAULTS.get(subject, UNKNOWN)


def is_generic(klass: int, subject: int, detail: int) -> bool:
    """Whether a code says too little on its own, so the diagnostic text may refine it: ``x.0.x``, ``x.y.0``,
    ``5.5.x``, ``5.7.1`` and ``4.7.x`` (except the codes that decide on their own)."""
    if specific(klass, subject, detail) is not None:
        return False
    if subject == 0 or detail == 0:
        return True
    return (klass, subject) in ((5, 5), (4, 7)) or (klass, subject, detail) == (5, 7, 1)

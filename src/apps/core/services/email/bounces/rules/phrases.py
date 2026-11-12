"""Diagnostic phrases that refine a generic code, or a report without one, in order: the first match wins.

Sender-side rejections come first (a relay refusal or a spam verdict is never evidence against the address), then a
disabled mailbox, a missing address, a full mailbox, a message too large, the temporary failures and the recipient's
policy. The wording follows Exchange Online, Gmail, Yahoo and gateways (Proofpoint, Postfix, Exim, qmail). Each
pattern is literal alternatives with bounded gaps, matched against at most 1,000 lower-case, whitespace-collapsed
characters, so hostile input stays linear.

"Mailbox unavailable" is deliberately not a missing address: RFC 5321 gives it for policy refusals too.
"""

import re
from dataclasses import dataclass

from .codes import DISABLED, FULL, HARD, POLICY, RELAY, SPAM, TRANSIENT, Category


@dataclass(frozen=True)
class Phrase:
    category: str
    reason: str
    pattern: re.Pattern


def _phrase(category: str, reason: str, *alternatives: str) -> Phrase:
    return Phrase(category, reason, re.compile("|".join(alternatives)))


SIZE = _phrase(
    TRANSIENT,
    "Message too large",
    r"\btoo (?:large|big)\b|\bsize ?limit|\bmessage (?:size|length)\b|\bmax(?:imum)? (?:message |receive )?size\b",
)
# A size limit of 0: the mailbox takes nothing at all, which is how servers disable one ("max size allowed: 0 KB").
# The disabled mailbox wins over "message too large" then: the message's size is not the problem.
ZERO_LIMIT_RE = re.compile(
    r"\b(?:max(?:imum)?|limit|allowed)\b[^0-9.;]{0,40}?(?<![\d.])0(?:\.0+)? ?(?:[kmg]i?b|bytes?|k)\b"
)
ZERO_LIMIT = Phrase(
    DISABLED, "Recipient mailbox accepts no messages (0 KB size limit): treated as disabled", ZERO_LIMIT_RE
)
PHRASES = (
    _phrase(
        RELAY,
        "Relay denied: the receiving server would not take our message by this route",
        r"\brelay(?:ing)? (?:access )?(?:is )?(?:denied|refused|prohibited|not (?:permitted|allowed))",
        r"\b(?:unable|not (?:permitted|allowed)|cannot|can't) (?:to )?relay\b|\bwe do not relay\b",
        r"\btenantattribution\b|\ballowed rcpthosts\b",
    ),
    _phrase(
        SPAM,
        "Rejected as spam, or for our sending reputation or authentication",
        r"spam|unsolicited|\b(?:junk|bulk) e?-?mail\b|\bphish|\bvirus|\bmalware|\bsuspicious\b",
        r"\b(?:block|black|deny) ?-?list|\b(?:rbl|dnsbl|surbl|ipcheck)\b",
        r"reputation|content filter|\bbanned\b|\bblocked using\b|\bpolicy reasons\b|\b(?:tss0\d|ts0\d|ph01|bl2\d)\b",
        r"\b(?:dmarc|spf|dkim)\b|\bunauthenticated\b|\bauthentication (?:fail|check)",
        r"\breverse dns\b|\bptr record|\brdns\b|\bcannot find your (?:reverse )?hostname\b",
        r"\bsender (?:address|domain)\b[^.;]{0,30}?\b(?:rejected|refused|invalid|not found|does not exist)\b",
    ),
    _phrase(
        DISABLED,
        "Recipient mailbox is disabled",
        r"(?<!sender )(?<!sending )(?<!your )\b(?:account|mailbox|user|recipient|inbox)\b[^.;:]{0,40}?"
        r"\b(?:is|has been|was) (?:disabled|deactivated|suspended|inactive|closed)\b",
        r"(?<!sender )(?<!your )\b(?:account|mailbox|user|inbox) (?:disabled|deactivated|suspended|inactive)\b",
        r"\b(?:disabled|deactivated|suspended|inactive) (?:account|mailbox|user|inbox)\b|\b554\.30\b",
    ),
    _phrase(
        HARD,
        "Recipient address does not exist",
        r"\buser unknown\b|\bunknown (?:user|recipient|mailbox|addressee)\b|\baddressee unknown\b",
        r"\bno such (?:user|mailbox|recipient|address|account|person)\b|\bno mailbox (?:here|by that name)\b",
        r"\b(?:recipient|address|mailbox|account|user)\b[^.;:]{0,40}?\b(?:does not|doesn't|did not) exist\b",
        r"\bdoes(?:n't| not) have an? [\w.-]{1,40} account\b",
        r"\brecipient (?:not found|unknown|invalid)\b|\brecipientnotfound\b|\binvalid (?:recipient|mailbox)\b",
        r"\bmailbox (?:not found|unknown)\b|\baddress (?:not found|(?:could ?n[o']t|cannot|can't) be found)\b",
        r"\bunrout(?:e)?able address\b|\bnot a valid (?:user|recipient|mailbox)\b|\bnxdomain\b",
        r"\bnon-?existent (?:domain|user|mailbox|address|recipient)\b",
        r"\bhost (?:or domain name )?not found\b(?!,? try again)|\bdomain (?:name )?(?:not found|does not exist)\b",
    ),
    _phrase(
        FULL,
        "Recipient mailbox is full",
        r"\b(?:mailbox|mail box|inbox|account|disk|user|recipient)\b[^.;:]{0,20}?\b(?:is )?full\b",
        r"\bover ?quota\b|\bquota (?:exceeded|full|reached)\b|\bexceed(?:s|ed)? (?:the |its )?(?:storage|quota)\b",
        r"\bout of storage\b|\binsufficient (?:storage|disk space)\b|\bstorage (?:allocation )?exceeded\b",
        r"\bexceeded storage allocation\b|\bmailbox (?:size )?limit exceeded\b",
    ),
    SIZE,
    _phrase(TRANSIENT, "Connection timed out", r"\btimed? ?-?out\b|\b(?:winsock|socket) error code:? ?10060\b"),
    _phrase(
        TRANSIENT,
        "Could not connect to the recipient's mail server",
        r"\bconnection (?:refused|reset|dropped|closed|lost|failed|attempt failed)\b|\bno route to host\b",
        r"\b(?:could not|couldn't|unable to|failed to|cannot|can't) (?:establish (?:a )?)?connect(?:ion)?\b",
        r"\b(?:network|host) (?:is )?unreachable\b|\b(?:winsock|socket) error\b",
    ),
    _phrase(
        TRANSIENT,
        "DNS lookup failed",
        r"\bdns\b[^.;:]{0,30}?\b(?:fail(?:ed|ure)?|error|timeout|problem)\b|\bservfail\b",
    ),
    _phrase(TRANSIENT, "Delivery expired after retries", r"\bexpired\b|\bgiving up\b|\bgave up\b"),
    _phrase(TRANSIENT, "Mail routing loop", r"\bmail loop\b|\bloop(?:ing)? detected\b|\bhop count\b|\btoo many hops\b"),
    _phrase(
        TRANSIENT,
        "Temporary failure: the server asked to try again later",
        r"\b(?:try|come back|retry)(?: again)? later\b|\btry again\b|\btemporar(?:y|ily)\b|\bdeferr?(?:ed|al)\b",
        r"\bgr[ae]y ?-?list|\brate ?-?limit|\bthrottl|\btoo many (?:connections|messages|recipients|concurrent|sessions)\b|\bserver (?:is )?busy\b",
        r"\bservice (?:is )?(?:temporarily |currently )?(?:not available|unavailable)\b",
        r"\binsufficient system (?:storage|resources)\b",
    ),
    _phrase(
        POLICY,
        "Rejected by the recipient's server policy",
        r"\bpolic(?:y|ies)\b|\bnot (?:authori[sz]ed|permitted|allowed)\b|\baccess denied\b|\bprohibited\b",
        r"\bsender (?:is )?(?:denied|blocked)\b|\bblocked sender\b|\brestrict(?:ed|ion)\b|\bmoderat(?:ed|ion|or)\b",
        r"\bauthentication required\b|\bauthrequired\b|\bnotauthorized\b|\bonly (?:accepts?|receives?)\b",
        r"\brejected by (?:the )?(?:recipient|administrator|organi[sz]ation|transport rule)\b",
    ),
)
ALL = frozenset(Category.values)
# What a phrase may make of a code: a temporary failure only a sender-side rejection or a full mailbox; 5.7.0 and
# 5.7.1 (security or policy) never a temporary failure; an ambiguous code (codes.AMBIGUOUS) only a temporary one.
TEMPORARY_REFINEMENTS = frozenset({RELAY, SPAM, FULL})
POLICY_REFINEMENTS = frozenset({RELAY, SPAM, DISABLED, HARD, POLICY})
AMBIGUOUS_REFINEMENTS = frozenset({TRANSIENT})


def refine(text: str, allowed) -> Phrase | None:
    """The first phrase in ``text`` (lower case) whose category is ``allowed``; a size limit of 0 is a disabled
    mailbox."""
    for phrase in PHRASES:
        if phrase.category in allowed and phrase.pattern.search(text):
            if phrase is SIZE and DISABLED in allowed and ZERO_LIMIT_RE.search(text):
                return ZERO_LIMIT
            return phrase
    return None

"""Automatic replies: the headers that mark one, what its own text says (an absence, or that the person left), the
address a left-the-organisation notice names instead, and whether a message may ever be answered automatically.

A reply's quoted original (Outlook's header block, also as an HTML-only message's text gives it, "On … wrote:", ">"
lines, an original- or forwarded-message banner) is cut off before any phrase is read, and a reply's or automatic
reply's subject ("RE: …", "Automatic reply: …") adds no words, so the site's own campaign text and subject, sent
back, never decide anything. A notice that mentions an absence is an out-of-office reply even when it also says
someone left, and "nobody reads this mailbox" alone is no notice that someone left: an out-of-office reply is never
evidence against an address. The address a notice names is a hint only: never verified, never applied.
Pure functions: no database, no network.
"""

import re
from typing import NamedTuple

from .headers import first
from .rules import (
    ABSENCE_RE,
    AUTO_REPLY,
    AUTO_REPLY_HEADERS,
    AUTO_REPLY_SUBJECT_RE,
    BULK_PRECEDENCE,
    EXCHANGE_RULE_HEADERS,
    LEFT_ORG,
    LEFT_ORG_RE,
    LIST_HEADERS,
    NOREPLY_RE,
    REPLY_SUBJECT_RE,
    REPORT_SENDERS,
    SYSTEM,
    VACATION_RE,
)

# How much of the decoded text the content rules read.
TEXT_HEAD_CHARS = 4096
# Addresses read from one notice's text, and how far before one the words that introduce it are read.
MAX_ADDRESSES = 20
CUE_CHARS = 120
VACATION, OTHER = "vacation", "other"
NEW_ADDRESS, CONTACT, MENTIONED = "new_address", "contact", "mentioned"

QUOTE_START_RE = re.compile(
    r"^(?:_{10,}|-{2,} ?(?:original message|forwarded message|mensaje original|message d[’']origine|"
    r"urspr[üu]ngliche nachricht|messaggio originale|mensagem original|oorspronkelijk bericht)|"
    r"(?:from|de|von|da|van) ?:[^\n]{0,300}\n(?:[^\n]{0,300}\n){0,4}? ?"
    r"(?:sent|date|enviado|envoy[ée]|gesendet|datum|data|fecha|inviato|verzonden) ?:|"
    r"(?:on|el|le|am|em|il|op) [^\n]{1,200}(?:wrote|escribi[óo]|a [ée]crit|schrieb|escreveu|ha scritto|schreef)"
    r"[^\n]{0,120}:|>)",
    re.IGNORECASE | re.MULTILINE,
)
EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.+-]{1,64}@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?){1,8}",
    re.IGNORECASE,
)
_SENTENCE_END_RE = re.compile(r"[.!?;]\s|\n\s*\n")
# Runs of spaces, tabs and no-break spaces (HTML text is full of them): one space, so the phrases match.
_SPACES_RE = re.compile(r"[^\S\n]+")
# Words just before an address that introduce the person's own new address...
NEW_ADDRESS_CUE_RE = re.compile(
    r"\bnew (?:e-?mail|mail|contact|address)|\b(?:reach|reached|find|contact) (?:me|him|her|them) (?:now )?at\b|"
    r"\bnow (?:at|reachable at|using)\b|\bnuev[oa] (?:correo|direcci[óo]n|e-?mail)|\bnouvelle adresse|"
    r"\bneue (?:e-?mail-?)?adresse|\bnov[oa] (?:e-?mail|endere[çc]o)|\bnuovo indirizzo|\bnieuwe? (?:e-?mail)?adres",
    re.IGNORECASE,
)
# ...or someone to contact instead.
CONTACT_CUE_RE = re.compile(
    r"\b(?:contact|reach out to|reach|e-?mail|write to|direct|forward|send|redirect|address|call|ask)\b|"
    r"\bcomun[íi]que(?:se)? con\b|\bcont[áa]cte(?:se|nos)?\b|\bescrib(?:a|ir|e) a\b|\bdir[íi]j(?:a|ase)\b|"
    r"\bcontactez\b|\b[ée]crire [àa]\b|\badress(?:ez|er)\b|\bwenden sie sich\b|\bkontaktier|\bschreiben sie\b|"
    r"\bcontatt|\bentre em contato\b|\bneem contact\b|\bstuur\b",
    re.IGNORECASE,
)
# X-Auto-Response-Suppress values that ask for no automatic reply (Exchange's own list).
_SUPPRESS_WORDS = ("all", "autoreply", "oof")


class Notice(NamedTuple):
    """An automatic reply as ``detect`` found it (``classify`` makes the verdict)."""

    classification: str
    subtype: str
    signals: tuple[str, ...]
    contact: str = ""
    contact_kind: str = ""


def own_text(text: str) -> str:
    """What a message wrote itself: its text up to the quoted original, at most ``TEXT_HEAD_CHARS``."""
    text = _SPACES_RE.sub(" ", str(text or "")[:TEXT_HEAD_CHARS])
    match = QUOTE_START_RE.search(text)
    return text[: match.start()] if match else text


def own_subject(subject: str) -> str:
    """A subject's own words: none for a reply's or an automatic reply's, whose rest is the original's subject."""
    subject = str(subject or "")
    return "" if AUTO_REPLY_SUBJECT_RE.match(subject) or REPLY_SUBJECT_RE.match(subject) else subject


def kind_of(text: str, *, notice: bool = False) -> str:
    """``vacation``, ``left_org`` or ``other``: what a notice's own words say. An absence wins over "left": an
    out-of-office reply that mentions a colleague who left, or a holiday closure, is still an out-of-office reply.
    ``notice``: its headers already make the message an automatic reply, so the wider absence wording names one too
    (without them, as with Exchange's rule markers alone, a person may have written it)."""
    if VACATION_RE.search(text):
        return VACATION
    left = bool(LEFT_ORG_RE.search(text))
    if (left or notice) and ABSENCE_RE.search(text):
        return VACATION
    return LEFT_ORG if left else OTHER


def _unusable(address: str) -> bool:
    local = address.partition("@")[0]
    return local in REPORT_SENDERS or bool(NOREPLY_RE.match(local))


def named_contact(text: str, exclude) -> tuple[str, str]:
    """The address a notice names instead of the one mailed, and how: ``new_address`` (the person's own new
    address), ``contact`` (someone to contact instead) or ``mentioned`` (the only address it names); ``("", "")``
    when there is none. ``exclude`` holds the sender's and the site's addresses (lower case)."""
    candidates: dict[str, str] = {}
    for match in EMAIL_RE.finditer(text):
        address = match.group(0).lower().strip(".")
        if address in exclude or address in candidates or _unusable(address):
            continue
        fragment = _SENTENCE_END_RE.split(text[max(0, match.start() - CUE_CHARS) : match.start()])[-1]
        if NEW_ADDRESS_CUE_RE.search(fragment):
            return address, NEW_ADDRESS
        candidates[address] = CONTACT if CONTACT_CUE_RE.search(fragment) else ""
        if len(candidates) >= MAX_ADDRESSES:
            break
    cued = [address for address, how in candidates.items() if how]
    if cued:
        return cued[0], CONTACT
    if len(candidates) == 1:
        return next(iter(candidates)), MENTIONED
    return "", ""


def _signals(evidence) -> tuple[list[str], list[str], bool]:
    """The automatic-reply signals, Exchange's rule markers, and whether the signals say "reply" (rather than only
    "auto-generated")."""
    headers = evidence.headers
    auto_submitted = first(headers, "auto-submitted").strip().lower()
    signals = ["auto_submitted"] if auto_submitted and not auto_submitted.startswith("no") else []
    vendor = [name for name in AUTO_REPLY_HEADERS if name in headers]
    if first(headers, "x-autogenerated").strip().lower().startswith("reply"):
        vendor.append("x-autogenerated")
    precedence = first(headers, "precedence").strip().lower() == "auto_reply"
    subject = bool(AUTO_REPLY_SUBJECT_RE.match(evidence.subject))
    signals += vendor + (["precedence_auto_reply"] if precedence else []) + (["auto_reply_subject"] if subject else [])
    replied = auto_submitted.startswith("auto-replied") or bool(vendor) or precedence or subject
    return signals, [name for name in EXCHANGE_RULE_HEADERS if name in headers], replied


def detect(evidence, own_addresses) -> Notice | None:
    """The automatic reply ``evidence`` is, or None. Exchange's rule markers alone need the wording of a notice (an
    absence, or that the person left): without it the message may be a person's, redirected by a rule."""
    signals, exchange, replied = _signals(evidence)
    if not signals and not exchange:
        return None
    text = own_text(evidence.text_head)
    kind = kind_of(f"{own_subject(evidence.subject)}\n{text}", notice=bool(signals))
    if not signals and kind == OTHER:
        return None
    found = tuple(signals + exchange)
    if kind == LEFT_ORG:
        contact, how = named_contact(text, {*own_addresses, evidence.from_address})
        return Notice(LEFT_ORG, LEFT_ORG, found, contact, how)
    if kind == OTHER and not replied:
        return Notice(SYSTEM, "auto_generated", found)
    return Notice(AUTO_REPLY, kind, found)


def response_allowed(evidence) -> bool:
    """Whether a person's message may be answered automatically (an acknowledgement, a notification), by RFC 3834
    §2: not when it came through a list or a bulk sender, asks for no automatic reply, or has no address to answer.
    Automated mail is never answered (the caller checks the class): answering an automatic reply starts a loop."""
    headers = evidence.headers
    auto_submitted = first(headers, "auto-submitted").strip().lower()
    if auto_submitted and not auto_submitted.startswith("no"):
        return False
    if any(name in headers for name in (*AUTO_REPLY_HEADERS, *EXCHANGE_RULE_HEADERS, *LIST_HEADERS)):
        return False
    if first(headers, "precedence").strip().lower() in (*BULK_PRECEDENCE, "auto_reply"):
        return False
    suppress = first(headers, "x-auto-response-suppress").lower()
    if any(word in suppress for word in _SUPPRESS_WORDS):
        return False
    address = evidence.from_address
    return bool(address) and first(headers, "return-path").strip() != "<>" and not _unusable(address)

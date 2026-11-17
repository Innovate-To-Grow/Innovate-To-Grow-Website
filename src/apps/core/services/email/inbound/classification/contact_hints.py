"""Unverified contact hints from the own text of a left-the-organisation automatic reply."""

import re

from .rules import NOREPLY_RE, REPORT_SENDERS

# Addresses read from one notice's text, and how far before one the words that introduce it are read.
MAX_ADDRESSES = 20
CUE_CHARS = 120
NEW_ADDRESS, CONTACT, MENTIONED = "new_address", "contact", "mentioned"

# A name must follow an instruction to contact a person. A departing employee's name in "Jordan Park has left"
# is not an alternate contact. These are deliberately narrow hints for staff, not identity verification.
CONTACT_NAME_RE = re.compile(
    r"\b(?:please\s+)?(?:contact|call|email|e-mail|reach out to|reach)\s+"
    r"(?P<name>[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'’.-]+(?:\s+[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'’.-]+){1,3})\b"
)
PHONE_RE = re.compile(
    r"(?<![\w@])(?:\+?\d{1,3}[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}"
    r"(?:\s*(?:ext\.?|x)\s*\d{1,6})?(?![\w@])"
)

EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.+-]{1,64}@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?){1,8}",
    re.IGNORECASE,
)
_SENTENCE_END_RE = re.compile(r"[.!?;]\s|\n\s*\n")
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


def named_person(text: str) -> str:
    """A full name explicitly introduced as someone to contact; never infer one from the notice sender."""
    match = CONTACT_NAME_RE.search(text)
    return match.group("name")[:100].strip(" .-") if match else ""


def named_phone(text: str) -> str:
    """The first plausible phone in the notice's own text, ignoring digit strings in email addresses."""
    without_emails = EMAIL_RE.sub(" ", text)
    for match in PHONE_RE.finditer(without_emails):
        value = match.group(0).strip()
        digits = re.sub(r"\D", "", value.split("ext")[0].split(" x")[0])
        if 10 <= len(digits) <= 15:
            return value[:40]
    return ""

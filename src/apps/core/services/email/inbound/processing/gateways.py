"""Links that mail-security gateways wrapped, read for the link they hold (``scrub`` judges a wrapped link by it).

Microsoft Safe Links holds the link percent-encoded in ``url=``, right after its host or, for a link that opens in a
Microsoft 365 app (a Teams meeting, a Word file), after the app's path (``/ap/t-59584e83/``). Proofpoint URL Defense
v2 holds it in ``u=``, "-XX" for a character and "_" for "/"; v3 between ``__`` marks, a "*" for each character it
replaced ("**" and a letter for a run of them), those characters base64 after ``__;``. What follows the link is the
gateway's own: Safe Links' ``data=`` (the recipient and their mail flow), ``sdata=`` (its signature) and
``reserved=``, Proofpoint's ``d=``, ``c=``, ``r=``, ``m=``, ``s=`` and ``e=`` or v3's ``__;…!…$`` tail.
"""

import base64
import re
import string
from urllib.parse import unquote

# (v3's own "!!<customer>!<signature>$" tail is matched too, so the link it holds is read without it.)
_PROOFPOINT_RE = re.compile(
    r"(?i)https?://urldefense\.proofpoint\.com/v2/url\?u=([^&\s\"'<>]*)"
    r"|https?://urldefense\.com/v3/__([^\s\"'<>]*?)(?:__;([a-z0-9_-]*)(?:!![a-z0-9_!-]*\$)?|$)"
)
_SAFE_LINKS_RE = re.compile(
    r"(?i)https?://[a-z0-9.-]*safelinks\.protection\.outlook\.com/(?:ap/[a-z0-9]+-[0-9a-f]+/)?"
    r"\?(?:[^\s\"'<>#]*?[&;])?url=([^&\s\"'<>]*)"
)
# The gateway's own parameters after the link it holds (Safe Links' "data=" names the recipient, "pat%40example.edu"):
# never a "," "|" "(" or the like, which a sentence or a CSV row puts after a link.
_OWN_PARAMETERS_RE = re.compile(r"[A-Za-z0-9%&;=_.!$*+~-]*")
_V3_MARK_RE = re.compile(r"\*(?:\*(.))?")
_V3_RUNS = string.ascii_uppercase + string.ascii_lowercase + string.digits + "-_"  # a run of 2, 3, … characters


def _proofpoint(found) -> str:
    """The link a Proofpoint URL Defense wrapper holds."""
    v2, v3, characters = found.groups()
    if v2 is not None:
        return re.sub(r"-([0-9A-Fa-f]{2})", lambda hit: chr(int(hit.group(1), 16)), v2.replace("_", "/"))
    try:
        replaced = iter(base64.urlsafe_b64decode(f"{characters or ''}==").decode("utf-8", "replace"))
    except ValueError:
        replaced = iter("")

    def mark(hit) -> str:
        # A character that is lost reads as "#", the one a sign-in link's token follows.
        count = _V3_RUNS.find(hit.group(1)) + 2 if hit.group(1) else 1
        return "".join(next(replaced, "#") for _ in range(count))

    return _V3_MARK_RE.sub(mark, v3)


def unwrapped(value: str) -> str:
    """``value`` with JSON's "\\/" read as "/", and each Proofpoint wrapper replaced by the link it holds."""
    return _PROOFPOINT_RE.sub(_proofpoint, value.replace("\\/", "/"))


def is_proofpoint(link: str) -> bool:
    """Whether ``link`` (JSON-escaped or not) is a Proofpoint URL Defense wrapper."""
    return _PROOFPOINT_RE.match(link.replace("\\/", "/")) is not None


def held(link: str) -> tuple[int, int, int, str] | None:
    """For a Safe Links or Proofpoint wrapper ``link``: where the link it holds starts and ends in it, where the
    gateway's own parameters after it end, and that link decoded. None for any other link."""
    found = _SAFE_LINKS_RE.match(link)
    if found is not None:
        start, end, inner = *found.span(1), unquote(found.group(1))
    elif (found := _PROOFPOINT_RE.match(link)) is not None:
        start, end = found.span(1 if found.group(1) is not None else 2)
        inner = _proofpoint(found)
    else:
        return None
    return start, end, _OWN_PARAMETERS_RE.match(link, end).end(), inner

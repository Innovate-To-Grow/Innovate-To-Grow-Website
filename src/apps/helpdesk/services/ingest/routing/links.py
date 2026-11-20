"""Links that mail-security gateways rewrote, read for where they go before the scam checks judge them (``scam``).

Microsoft Safe Links (``url=``), Proofpoint URL Defense (v2 ``u=``, v3 the link between ``__`` marks) and Barracuda
Link Protection (``a=``) carry the whole link. Mimecast URL Protect names only the host it goes to (``?domain=``), so
its link is judged as that host's. A wrapper that cannot be read stays as it is: judged as the gateway's own link, so
a link text naming another domain is still a mismatch.
"""

import html as html_lib
import re
from urllib.parse import parse_qs, urlsplit

_WRAPPED_RE = re.compile(
    r"https://(?:[a-z0-9.-]*safelinks\.protection\.outlook\.com/\?|urldefense\.proofpoint\.com/v2/url\?|"
    r"urldefense\.com/v3/__|linkprotect\.cudasvc\.com/url\?|protect[a-z0-9-]*\.mimecast\.com/s/|"
    r"url\.[a-z0-9-]+\.m\.mimecastprotect\.com/s/)[^\s\"'<>]+",
    re.IGNORECASE,
)
# The query parameter holding the link, by the wrapper's host (Safe Links' hosts vary by region: "url").
_PARAMETER = {"urldefense.proofpoint.com": "u", "linkprotect.cudasvc.com": "a"}
_HOST_RE = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", re.IGNORECASE)


def _unwrapped(match) -> str:
    wrapped = html_lib.unescape(match.group(0))
    parts = urlsplit(wrapped)
    host, query = (parts.hostname or "").lower(), parse_qs(parts.query)
    if host == "urldefense.com" and "/v3/__" in wrapped:
        inner = wrapped.split("/v3/__", 1)[1].split("__;", 1)[0]
    elif host.endswith((".mimecast.com", ".mimecastprotect.com")):
        # A trailing "." or ")" is the sentence's, as in a text part.
        domain = (query.get("domain") or [""])[0].rstrip(".,;:!?)")
        inner = f"https://{domain}/" if _HOST_RE.fullmatch(domain) else ""
    else:
        inner = (query.get(_PARAMETER.get(host, "url")) or [""])[0]
        if host == "urldefense.proofpoint.com":  # v2 writes "-3A" for ":" and "_" for "/"
            inner = re.sub(r"-([0-9A-Fa-f]{2})", lambda hit: chr(int(hit.group(1), 16)), inner.replace("_", "/"))
    # Quoted, so the link cannot end the HTML attribute it stands in.
    return (inner or match.group(0)).replace('"', "%22").replace("'", "%27")


def unwrap_links(value: str) -> str:
    return _WRAPPED_RE.sub(_unwrapped, value or "")

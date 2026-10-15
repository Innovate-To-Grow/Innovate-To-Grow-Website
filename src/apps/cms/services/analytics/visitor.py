"""The page-view visitor id: an opaque random id the browser keeps and sends with each page view.

Most visitors share the campus public IP, so the IP cannot tell them apart, neither for the page-view throttle nor
for the unique-visitor statistics. The frontend therefore generates a random id (a UUID kept in localStorage) and
posts it as ``visitor_id``. It is unsigned and client-chosen: good enough to count visitors and to keep one browser
from flooding the endpoint, never an identity and never a security control.
"""

import re

VISITOR_ID_MAX_LENGTH = 64

# A UUID in its usual text form, or any other token of up to 64 URL-safe characters. The id ends up in a cache key
# and in a 64-character column, so nothing else is accepted.
_VISITOR_ID = re.compile(rf"[A-Za-z0-9_-]{{1,{VISITOR_ID_MAX_LENGTH}}}")


def clean_visitor_id(value) -> str | None:
    """Return ``value`` when it is a well-formed visitor id, else ``None`` (the page view is then recorded without).

    A malformed id is ignored rather than rejected: tracking must never fail a page view over it, and old cached
    frontend bundles send none at all.
    """
    if isinstance(value, str) and _VISITOR_ID.fullmatch(value):
        return value
    return None

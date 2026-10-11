"""HTML, link, and redirect rewriting for the CloudFront viewer origin."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .policies import (
    InvalidLegacyPath,
    PathDecision,
    canonicalize_legacy_path,
    classify_legacy_path,
    filter_query_string,
)

LEGACY_PUBLIC_HOSTS = {
    "35.86.48.145",
    "legacy.i2g.ucmerced.edu",
}

_URL_ATTRIBUTES = {
    "a": ("href",),
    "audio": ("src",),
    "iframe": ("src",),
    "img": ("src",),
    "link": ("href",),
    "script": ("src",),
    "source": ("src",),
    "track": ("src",),
    "video": ("poster", "src"),
}

_FORM_CONTROL_TAGS = {"button", "fieldset", "input", "option", "select", "textarea"}


@dataclass(frozen=True)
class RewrittenURL:
    value: str
    blocked: bool = False
    internal: bool = False


class InvalidLegacyURL(ValueError):
    """Raised when an origin-provided URL cannot be parsed safely."""


def _internal_url_parts(value: str, current_path: str, origin_host: str):
    stripped = value.strip()
    if not stripped or stripped.startswith("#"):
        return None

    try:
        parsed = urlsplit(stripped)
    except ValueError as exc:
        raise InvalidLegacyURL("Legacy origin returned an invalid URL.") from exc
    scheme = parsed.scheme.lower()
    if scheme in {"javascript", "vbscript"}:
        return False
    if scheme and scheme not in {"http", "https"}:
        return None

    base = f"http://{origin_host}{current_path}"
    try:
        resolved = urlsplit(urljoin(base, stripped))
        hostname = (resolved.hostname or "").lower()
    except ValueError as exc:
        raise InvalidLegacyURL("Legacy origin returned an invalid URL.") from exc
    internal_hosts = {*LEGACY_PUBLIC_HOSTS, origin_host.lower()}
    return resolved if hostname in internal_hosts else None


def rewrite_document_url(value: str, current_path: str, origin_host: str, viewer_base_url: str) -> RewrittenURL:
    try:
        parts = _internal_url_parts(value, current_path, origin_host)
    except InvalidLegacyURL:
        return RewrittenURL("#", blocked=True)
    if parts is False:
        return RewrittenURL("#", blocked=True)
    if parts is None:
        return RewrittenURL(value)

    try:
        canonical_path = canonicalize_legacy_path(parts.path)
        decision = classify_legacy_path(canonical_path)
    except InvalidLegacyPath:
        return RewrittenURL("#", blocked=True, internal=True)
    if decision is not PathDecision.ALLOW:
        return RewrittenURL("#", blocked=True, internal=True)
    rewritten = urlunsplit(
        (
            "https",
            urlsplit(viewer_base_url).netloc,
            canonical_path,
            filter_query_string(parts.query),
            parts.fragment,
        )
    )
    return RewrittenURL(rewritten, internal=True)


def rewrite_location(value: str, current_path: str, origin_host: str, viewer_base_url: str) -> str:
    """Keep external redirects external and route every internal redirect via CloudFront."""

    parts = _internal_url_parts(value, current_path, origin_host)
    if parts is False:
        return viewer_base_url
    if parts is None:
        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise InvalidLegacyURL("Legacy origin returned an invalid redirect URL.") from exc
        return value if parsed.scheme in {"http", "https"} else viewer_base_url
    try:
        canonical_path = canonicalize_legacy_path(parts.path)
    except InvalidLegacyPath:
        return viewer_base_url
    return urlunsplit(
        (
            "https",
            urlsplit(viewer_base_url).netloc,
            canonical_path,
            filter_query_string(parts.query),
            parts.fragment,
        )
    )


def _rewrite_srcset(value: str, current_path: str, origin_host: str, viewer_base_url: str) -> str:
    candidates: list[str] = []
    for candidate in value.split(","):
        pieces = candidate.strip().split(maxsplit=1)
        if not pieces:
            continue
        rewritten = rewrite_document_url(pieces[0], current_path, origin_host, viewer_base_url)
        if rewritten.blocked:
            continue
        candidates.append(" ".join([rewritten.value, *pieces[1:]]))
    return ", ".join(candidates)


def rewrite_legacy_html(html: str, current_path: str, origin_host: str, viewer_base_url: str) -> str:
    """Make the old document visibly and mechanically read-only."""

    soup = BeautifulSoup(html, "html.parser")

    for base_tag in soup.find_all("base"):
        base_tag.decompose()
    for meta_tag in soup.find_all("meta"):
        if str(meta_tag.get("http-equiv", "")).lower() == "refresh":
            meta_tag.decompose()

    for form in soup.find_all("form"):
        form["action"] = "#"
        form["method"] = "get"
        form["inert"] = ""
        form["aria-disabled"] = "true"
        for event_attribute in [attribute for attribute in form.attrs if attribute.lower().startswith("on")]:
            del form[event_attribute]

    for control in soup.find_all(list(_FORM_CONTROL_TAGS)):
        control["disabled"] = ""
        control["aria-disabled"] = "true"

    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        removed = False
        for attribute in _URL_ATTRIBUTES.get(tag.name, ()):
            if attribute not in tag.attrs:
                continue
            rewritten = rewrite_document_url(str(tag.get(attribute, "")), current_path, origin_host, viewer_base_url)
            if rewritten.blocked:
                if tag.name == "a":
                    tag[attribute] = "#"
                    tag["aria-disabled"] = "true"
                    tag["data-legacy-write-disabled"] = "true"
                    tag["tabindex"] = "-1"
                    for event_attribute in [
                        current_attribute
                        for current_attribute in tag.attrs
                        if current_attribute.lower().startswith("on")
                    ]:
                        del tag[event_attribute]
                elif tag.name == "script":
                    # Removing only src could make fallback inline text execute,
                    # even though browsers ignore it when src is present.
                    tag.decompose()
                    removed = True
                    break
                else:
                    del tag[attribute]
            else:
                tag[attribute] = rewritten.value
        if removed:
            continue
        if "srcset" in tag.attrs:
            rewritten_srcset = _rewrite_srcset(str(tag["srcset"]), current_path, origin_host, viewer_base_url)
            if rewritten_srcset:
                tag["srcset"] = rewritten_srcset
            else:
                del tag["srcset"]

    banner = soup.new_tag("div", id="i2g-legacy-read-only-banner")
    banner["role"] = "status"
    banner["style"] = (
        "position:relative;z-index:2147483647;padding:12px 20px;background:#7a003c;color:#fff;"
        "font:600 16px/1.4 system-ui,sans-serif;text-align:center"
    )
    banner.string = "Legacy read-only — historical content only; forms and updates are disabled."
    if soup.body:
        soup.body.insert(0, banner)
    else:
        soup.insert(0, banner)
    return str(soup)

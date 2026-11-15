"""Adding the request nonce to the inline styles Unfold renders, so the policy needs no 'unsafe-inline'."""

import logging
import re

from django.conf import settings

# These methods used to live in ``csp_middleware``; keep that logger name.
logger = logging.getLogger("apps.core.middleware.csp_middleware")


class VendorStyleNonceMixin:
    """The vendor-style part of ``ContentSecurityPolicyMiddleware``."""

    _UNFOLD_THEME_STYLE_PATTERN = re.compile(
        r"<style\b(?P<attrs>[^>]*\bid=[\"']unfold-theme-colors[\"'][^>]*)>",
        flags=re.IGNORECASE,
    )

    _UNFOLD_CHANGELIST_STYLE_PATTERN = re.compile(
        r"<style\b(?P<attrs>[^>]*)>(?=\s*#changelist table thead th:first-child \{width: inherit\})",
        flags=re.IGNORECASE,
    )

    _NONCE_ATTRIBUTE_PATTERN = re.compile(r"\bnonce\s*=", flags=re.IGNORECASE)

    def _nonce_vendor_styles(self, response, nonce: str) -> None:
        """Attach the response nonce to inline styles from vendor templates.

        Unfold ships dynamic inline theme styles but does not expose a nonce
        hook. Rewriting style elements keeps those fragments compatible with
        enforcing CSP. Inline scripts are deliberately excluded and must opt
        in from a trusted template. Non-HTML, streaming, and encoded responses
        are left untouched.
        """

        if getattr(response, "streaming", False):
            return
        content_type = response.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            return
        if response.get("Content-Encoding", "").lower() not in {"", "identity"}:
            return

        charset = getattr(response, "charset", None) or settings.DEFAULT_CHARSET
        try:
            content = response.content.decode(charset)
        except (AttributeError, LookupError, UnicodeDecodeError):
            logger.exception("Unable to nonce CSP inline elements")
            return

        def _add_nonce(match: re.Match) -> str:
            attrs = match.group("attrs")
            if self._NONCE_ATTRIBUTE_PATTERN.search(attrs):
                return match.group(0)
            return f'<style{attrs} nonce="{nonce}">'

        # Source-owned inline elements opt in from trusted templates with
        # ``nonce="{{ request.csp_nonce }}"``. Automatically blessing every
        # rendered tag would turn otherwise-blocked HTML injection into
        # trusted markup. These two narrowly matched styles are the only
        # unavoidable inline blocks in Unfold's upstream templates.
        rewritten = self._UNFOLD_THEME_STYLE_PATTERN.sub(_add_nonce, content)
        rewritten = self._UNFOLD_CHANGELIST_STYLE_PATTERN.sub(_add_nonce, rewritten)
        if rewritten == content:
            return
        response.content = rewritten.encode(charset)
        if "Content-Length" in response:
            response["Content-Length"] = str(len(response.content))

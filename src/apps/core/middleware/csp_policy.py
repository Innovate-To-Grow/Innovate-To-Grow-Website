"""Building the Content-Security-Policy header: the configured sources, the origins of form actions, storage and
embeds, and the policy text the middleware sends."""

import logging
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.module_loading import import_string

# These methods used to live in ``csp_middleware``; keep that logger name.
logger = logging.getLogger("apps.core.middleware.csp_middleware")


class CspPolicyMixin:
    """The policy-building part of ``ContentSecurityPolicyMiddleware``."""

    _HOST_PATTERN = re.compile(
        r"^(?:\*\.)?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
    )

    @staticmethod
    def _configured_sources(setting_name: str, default: tuple[str, ...]) -> list[str]:
        return [str(source).strip() for source in getattr(settings, setting_name, default) if str(source).strip()]

    @staticmethod
    def _url_origin(value: object) -> str | None:
        """Return a CSP origin for an absolute HTTP(S) asset URL."""

        try:
            parsed = urlsplit(str(value or ""))
            hostname = parsed.hostname
            port = parsed.port
        except (TypeError, ValueError):
            return None
        if parsed.scheme not in {"http", "https"} or not hostname:
            return None
        rendered_host = f"[{hostname}]" if ":" in hostname else hostname
        rendered_port = f":{port}" if port is not None else ""
        return f"{parsed.scheme}://{rendered_host}{rendered_port}"

    def _form_action_origins(self, response) -> list[str]:
        """Return validated HTTPS origins a single response may post forms to.

        A view opts in per response (``response.csp_form_action_origins``);
        anything that is not an absolute HTTPS URL is dropped and only the
        origin is kept, so a path or script URL can never widen the policy.
        """

        origins = []
        for value in getattr(response, "csp_form_action_origins", ()) or ():
            origin = self._url_origin(value)
            if origin and origin.startswith("https://"):
                origins.append(origin)
        return list(dict.fromkeys(origins))

    def _storage_origins(self) -> list[str]:
        origins = []
        for setting_name in ("STATIC_URL", "MEDIA_URL"):
            origin = self._url_origin(getattr(settings, setting_name, ""))
            if origin:
                origins.append(origin)
        return list(dict.fromkeys(origins))

    # Directive -> (setting that overrides it, default sources).
    _CONFIGURABLE_SOURCES = {
        "script": ("CSP_SCRIPT_SOURCES", ("'self'", "https://cdn.jsdelivr.net")),
        "style": ("CSP_STYLE_SOURCES", ("'self'", "https://fonts.googleapis.com")),
        "font": ("CSP_FONT_SOURCES", ("'self'", "data:", "https://fonts.gstatic.com")),
        "image": ("CSP_IMAGE_SOURCES", ("'self'", "data:", "blob:")),
        "connect": ("CSP_CONNECT_SOURCES", ("'self'", "https://fonts.googleapis.com", "https://fonts.gstatic.com")),
    }

    def _configured_source_lists(self) -> dict[str, list[str]]:
        return {
            directive: self._configured_sources(setting, default)
            for directive, (setting, default) in self._CONFIGURABLE_SOURCES.items()
        }

    def _embed_frame_sources(self) -> list[str]:
        """``https://`` origins of the embeddable iframe hosts the apps register (see CSP_FRAME_HOST_PROVIDERS)."""
        try:
            # Apps contribute embeddable iframe hosts through CSP_FRAME_HOST_PROVIDERS
            # (dotted paths to zero-argument callables), so core imports no app.
            hosts = [
                host
                for provider in getattr(settings, "CSP_FRAME_HOST_PROVIDERS", ())
                for host in import_string(provider)()
            ]
            normalized_hosts = (host.strip().lower() for host in hosts)
            return [f"https://{host}" for host in normalized_hosts if self._HOST_PATTERN.fullmatch(host)]
        except Exception:
            # A policy lookup must never take the application down. Failing
            # closed leaves only same-origin frames until the cache/database
            # becomes healthy again.
            logger.exception("Unable to load CMS embed hosts for CSP; using same-origin only")
            return []

    def _build_policy(
        self,
        nonce: str,
        *,
        allow_framing: bool = False,
        form_action_origins: list[str] | None = None,
    ) -> str:
        storage_origins = self._storage_origins()
        sources = self._configured_source_lists()
        script_sources, style_sources = sources["script"], sources["style"]
        font_sources, image_sources, connect_sources = sources["font"], sources["image"], sources["connect"]
        frame_sources = ["'self'"]
        frontend_origin = self._url_origin(getattr(settings, "FRONTEND_URL", ""))
        if frontend_origin:
            frame_sources.append(frontend_origin)
            connect_sources.append(frontend_origin)
        frame_sources.extend(self._embed_frame_sources())

        nonce_source = f"'nonce-{nonce}'"
        media_sources = list(dict.fromkeys(["'self'", "blob:", *storage_origins]))
        form_action_sources = list(dict.fromkeys(["'self'", *(form_action_origins or [])]))
        directives = [
            "default-src 'self'",
            f"script-src {' '.join(dict.fromkeys([*script_sources, *storage_origins, nonce_source]))}",
            "script-src-attr 'none'",
            f"style-src {' '.join(dict.fromkeys([*style_sources, *storage_origins, nonce_source]))}",
            # Django Admin, Unfold, CodeMirror, and the vendored QR scanner
            # set presentation-only style attributes. Scope the compatibility
            # exception to attributes; style elements still require a nonce
            # and script handlers remain completely disabled.
            "style-src-attr 'unsafe-inline'",
            f"img-src {' '.join(dict.fromkeys([*image_sources, *storage_origins]))}",
            f"font-src {' '.join(dict.fromkeys([*font_sources, *storage_origins]))}",
            f"frame-src {' '.join(dict.fromkeys(frame_sources))}",
            f"connect-src {' '.join(dict.fromkeys(connect_sources))}",
            f"media-src {' '.join(media_sources)}",
            "worker-src 'self' blob:",
            "object-src 'none'",
            "base-uri 'self'",
            f"form-action {' '.join(form_action_sources)}",
            "report-uri /csp-report/",
        ]
        if not allow_framing:
            directives.insert(-1, "frame-ancestors 'none'")
        return "; ".join(directives)

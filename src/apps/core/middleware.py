import hashlib
import json
import logging
import re
import secrets
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

_SENSITIVE_CSP_PATH_SEGMENT = re.compile(
    r"(?P<prefix>/(?:invite|preview|resubscribe|unsubscribe)/)[^/]+",
    flags=re.IGNORECASE,
)


class HealthCheckMiddleware:
    """Health endpoints that bypass ALLOWED_HOSTS for ALB probes.

    `/livez/` checks only that the app process can respond. `/readyz/` and
    `/health/` check database readiness. `/health/` keeps the frontend-facing
    maintenance payload for backward compatibility.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/livez/":
            return self._json_response({"status": "ok"})
        if request.path in {"/readyz/", "/health/"}:
            return self._readiness_response()
        return self.get_response(request)

    def _readiness_response(self):
        # Import here to avoid circular imports.
        from django.db import DatabaseError, connection

        from apps.core.models import SiteMaintenanceControl

        health_status = {
            "status": "ok",
            "database": "ok",
            "maintenance": False,
            "maintenance_message": "",
        }

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except (DatabaseError, OSError) as e:
            logger.warning("Health check database probe failed: %s", e)
            health_status["status"] = "error"
            health_status["database"] = "unavailable"
            return self._json_response(health_status, status=503)

        try:
            config = SiteMaintenanceControl.load()
            if config.is_maintenance:
                health_status["status"] = "maintenance"
                health_status["maintenance"] = True
                health_status["maintenance_message"] = config.message
        except (DatabaseError, OSError):
            logger.exception("Failed to load SiteMaintenanceControl configuration during health check")

        return self._json_response(health_status)

    @staticmethod
    def _json_response(payload, *, status=200):
        return HttpResponse(json.dumps(payload), content_type="application/json", status=status)


class ContentSecurityPolicyMiddleware:
    """Add the configured CSP using the CMS iframe policy as its source of truth."""

    _HOST_PATTERN = re.compile(
        r"^(?:\*\.)?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
    )
    _UNFOLD_THEME_STYLE_PATTERN = re.compile(
        r"<style\b(?P<attrs>[^>]*\bid=[\"']unfold-theme-colors[\"'][^>]*)>",
        flags=re.IGNORECASE,
    )
    _UNFOLD_CHANGELIST_STYLE_PATTERN = re.compile(
        r"<style\b(?P<attrs>[^>]*)>(?=\s*#changelist table thead th:first-child \{width: inherit\})",
        flags=re.IGNORECASE,
    )
    _NONCE_ATTRIBUTE_PATTERN = re.compile(r"\bnonce\s*=", flags=re.IGNORECASE)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Make the nonce available before template rendering. Source-owned
        # templates opt in explicitly; the response rewriter below is limited
        # to two unavoidable styles from the upstream admin theme.
        request.csp_nonce = secrets.token_urlsafe(24)
        response = self.get_response(request)
        if "Content-Security-Policy" in response or "Content-Security-Policy-Report-Only" in response:
            return response

        report_only = getattr(settings, "CSP_REPORT_ONLY", True)
        header_name = "Content-Security-Policy-Report-Only" if report_only else "Content-Security-Policy"
        response[header_name] = self._build_policy(
            request.csp_nonce,
            allow_framing=bool(getattr(response, "xframe_options_exempt", False)),
        )
        self._nonce_vendor_styles(response, request.csp_nonce)
        return response

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

    def _storage_origins(self) -> list[str]:
        origins = []
        for setting_name in ("STATIC_URL", "MEDIA_URL"):
            origin = self._url_origin(getattr(settings, setting_name, ""))
            if origin:
                origins.append(origin)
        return list(dict.fromkeys(origins))

    def _build_policy(
        self,
        nonce: str,
        *,
        allow_framing: bool = False,
    ) -> str:
        storage_origins = self._storage_origins()
        script_sources = self._configured_sources(
            "CSP_SCRIPT_SOURCES",
            ("'self'", "https://cdn.jsdelivr.net"),
        )
        style_sources = self._configured_sources(
            "CSP_STYLE_SOURCES",
            ("'self'", "https://fonts.googleapis.com"),
        )
        font_sources = self._configured_sources(
            "CSP_FONT_SOURCES",
            ("'self'", "data:", "https://fonts.gstatic.com"),
        )
        image_sources = self._configured_sources(
            "CSP_IMAGE_SOURCES",
            ("'self'", "data:", "blob:"),
        )
        connect_sources = self._configured_sources(
            "CSP_CONNECT_SOURCES",
            ("'self'", "https://fonts.googleapis.com", "https://fonts.gstatic.com"),
        )
        frame_sources = ["'self'"]
        frontend_origin = self._url_origin(getattr(settings, "FRONTEND_URL", ""))
        if frontend_origin:
            frame_sources.append(frontend_origin)
            connect_sources.append(frontend_origin)
        try:
            from apps.cms.services.embed_hosts import get_allowed_hosts

            for host in get_allowed_hosts():
                normalized = host.strip().lower()
                if self._HOST_PATTERN.fullmatch(normalized):
                    frame_sources.append(f"https://{normalized}")
        except Exception:
            # A policy lookup must never take the application down. Failing
            # closed leaves only same-origin frames until the cache/database
            # becomes healthy again.
            logger.exception("Unable to load CMS embed hosts for CSP; using same-origin only")

        nonce_source = f"'nonce-{nonce}'"
        media_sources = list(dict.fromkeys(["'self'", "blob:", *storage_origins]))
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
            "form-action 'self'",
            "report-uri /csp-report/",
        ]
        if not allow_framing:
            directives.insert(-1, "frame-ancestors 'none'")
        return "; ".join(directives)

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


def _csp_report_rate_limited(request) -> bool:
    """Return whether this client exceeded the bounded CSP report window."""

    limit = max(int(getattr(settings, "CSP_REPORT_RATE_LIMIT", 60)), 1)
    window = max(int(getattr(settings, "CSP_REPORT_RATE_WINDOW_SECONDS", 60)), 1)
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if getattr(settings, "NUM_PROXIES", None) and forwarded_for:
        parts = [part.strip() for part in forwarded_for.split(",") if part.strip()]
        ident = parts[-1] if parts else request.META.get("REMOTE_ADDR", "unknown")
    else:
        ident = request.META.get("REMOTE_ADDR", "unknown")
    digest = hashlib.sha256(str(ident).encode("utf-8", errors="replace")).hexdigest()
    key = f"csp-report-rate:{digest}"
    try:
        if cache.add(key, 1, timeout=window):
            return False
        return cache.incr(key) > limit
    except Exception:
        # Reporting is diagnostic. A cache outage must not affect application
        # traffic, and downstream log-volume controls remain in place.
        logger.exception("Unable to apply CSP report rate limit")
        return False


@require_POST
@csrf_exempt
def csp_report(request):
    """Log CSP violation reports posted by the browser.

    Browsers POST a JSON report to this endpoint when a CSP rule is violated.
    We log at WARNING level so ops can observe violation patterns in CloudWatch
    before promoting the header from report-only to enforcing.

    The endpoint is publicly reachable, so the body is attacker-controlled.
    We parse it as JSON and log only the specific fields we care about — this
    prevents log-injection (forged newlines, ANSI escapes) and drops the raw
    bytes on the floor if the payload isn't a real report.
    """
    try:
        if _csp_report_rate_limited(request):
            return HttpResponse(status=204)

        try:
            content_length = int(request.META.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            content_length = 0
        if content_length > 4096:
            return HttpResponse(status=413)

        raw = request.body[:4096]
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except (ValueError, UnicodeDecodeError):
            logger.warning("CSP report with unparseable body (%d bytes)", len(raw))
            return HttpResponse(status=204)

        report = payload.get("csp-report") if isinstance(payload, dict) else None
        if not isinstance(report, dict):
            logger.warning("CSP report missing 'csp-report' object")
            return HttpResponse(status=204)

        def _clean(value: object) -> str:
            # Drop control chars (including newlines) so an attacker can't
            # forge extra log lines. 256-char cap per field keeps log volume
            # bounded even under spray. Two-step strip: explicit `\r` / `\n`
            # removal is the pattern CodeQL recognizes as a log-injection
            # sanitizer; the printable-char filter follows to also catch
            # ANSI escapes and other control bytes.
            s = str(value) if value is not None else ""
            s = s.replace("\r", " ").replace("\n", " ")
            s = "".join(ch for ch in s if ch.isprintable())
            try:
                parsed = urlsplit(s)
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    # Reports can include signed or callback URLs. Keep the
                    # route useful for diagnostics but never log credentials,
                    # query parameters, or fragments.
                    host = parsed.hostname
                    if ":" in host:
                        host = f"[{host}]"
                    try:
                        parsed_port = parsed.port
                    except ValueError:
                        parsed_port = None
                    port = f":{parsed_port}" if parsed_port is not None else ""
                    path = _SENSITIVE_CSP_PATH_SEGMENT.sub(
                        r"\g<prefix><redacted>",
                        parsed.path,
                    )
                    s = f"{parsed.scheme}://{host}{port}{path}"
            except (TypeError, ValueError):
                pass
            return s[:256]

        directive = _clean(report.get("violated-directive") or report.get("effective-directive"))
        blocked = _clean(report.get("blocked-uri"))
        document = _clean(report.get("document-uri"))
        source = _clean(report.get("source-file"))
        logger.warning(
            "CSP violation: directive=%s blocked=%s document=%s source=%s",
            directive,
            blocked,
            document,
            source,
        )
    except Exception:
        logger.exception("Unexpected error processing CSP violation report")
    return HttpResponse(status=204)

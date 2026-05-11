import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


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

        from core.models import SiteMaintenanceControl

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
            health_status["status"] = "error"
            health_status["database"] = str(e)
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
    """Add a Content-Security-Policy-Report-Only header to all responses.

    Starts in report-only mode so it doesn't break anything.
    Promote to enforcing (``Content-Security-Policy``) after monitoring.

    Violations are reported to ``/csp-report/`` — that endpoint logs them so
    we can tighten the policy (especially ``style-src 'unsafe-inline'``)
    before promoting to enforcing mode.
    """

    CSP_HEADER = (
        "default-src 'self'; "
        "script-src 'self' https://esm.run https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "frame-src 'self' https://www.youtube.com https://*.youtube.com "
        "https://www.youtube-nocookie.com https://*.youtube-nocookie.com "
        "https://player.vimeo.com https://*.vimeo.com "
        "https://docs.google.com https://forms.google.com https://www.google.com "
        "https://calendly.com https://*.calendly.com "
        "https://www.figma.com "
        "https://codesandbox.io https://*.codesandbox.io "
        "https://www.typeform.com https://form.typeform.com; "
        "connect-src 'self'; "
        "report-uri /csp-report/"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "Content-Security-Policy" not in response:
            response["Content-Security-Policy-Report-Only"] = self.CSP_HEADER
        return response


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
            return "".join(ch for ch in s if ch.isprintable())[:256]

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

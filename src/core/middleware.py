import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


class HealthCheckMiddleware:
    """Health check endpoint that bypasses ALLOWED_HOSTS for ALB probes.

    This middleware intercepts `/health/` before Django's SecurityMiddleware
    runs, which means the request's Host header is not validated against
    ALLOWED_HOSTS. This is intentional so AWS ALB/ELB probes (which use the
    instance's private IP as the Host header) succeed. The response only
    exposes DB connectivity and the `maintenance_message` string from
    SiteMaintenanceControl — both of which are non-sensitive.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            # Import here to avoid circular imports
            from django.db import DatabaseError, connection

            from .models import SiteMaintenanceControl

            health_status = {
                "status": "ok",
                "database": "ok",
                "maintenance": False,
                "maintenance_message": "",
            }

            # Check database connectivity
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            except (DatabaseError, OSError) as e:
                health_status["status"] = "error"
                health_status["database"] = str(e)
                return HttpResponse(json.dumps(health_status), content_type="application/json", status=503)

            # Check maintenance mode (return 200 so ALB health checks still pass)
            try:
                config = SiteMaintenanceControl.load()
                if config.is_maintenance:
                    health_status["status"] = "maintenance"
                    health_status["maintenance"] = True
                    health_status["maintenance_message"] = config.message
            except (DatabaseError, OSError):
                # Log maintenance configuration lookup errors but do not fail the health check.
                logger.exception("Failed to load SiteMaintenanceControl configuration during health check")

            return HttpResponse(json.dumps(health_status), content_type="application/json")
        return self.get_response(request)


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
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "frame-src https://www.youtube.com https://player.vimeo.com; "
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
    """
    try:
        body = request.body.decode("utf-8", errors="replace")[:4096]
        logger.warning("CSP violation report: %s", body)
    except Exception:
        logger.exception("Failed to parse CSP violation report")
    return HttpResponse(status=204)

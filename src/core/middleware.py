import json
import logging

from django.http import HttpResponse

logger = logging.getLogger(__name__)


class HealthCheckMiddleware:
    """Health check endpoint that bypasses ALLOWED_HOSTS for ALB probes.

    Returns database connectivity and maintenance mode status.
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
    """

    CSP_HEADER = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "frame-src https://www.youtube.com https://player.vimeo.com; "
        "connect-src 'self'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "Content-Security-Policy" not in response:
            response["Content-Security-Policy-Report-Only"] = self.CSP_HEADER
        return response

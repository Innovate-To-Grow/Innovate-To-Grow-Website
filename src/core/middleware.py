import json

from django.http import HttpResponse


class HealthCheckMiddleware:
    """Health check endpoint that bypasses ALLOWED_HOSTS for ALB probes.

    Returns database connectivity and maintenance mode status.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            # Import here to avoid circular imports
            from django.db import connection

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
            except Exception as e:
                health_status["status"] = "error"
                health_status["database"] = str(e)
                return HttpResponse(
                    json.dumps(health_status), content_type="application/json", status=503
                )

            # Check maintenance mode
            try:
                config = SiteMaintenanceControl.load()
                if config.is_maintenance:
                    health_status["status"] = "maintenance"
                    health_status["maintenance"] = True
                    health_status["maintenance_message"] = config.message
                    return HttpResponse(
                        json.dumps(health_status), content_type="application/json", status=503
                    )
            except Exception:
                pass

            return HttpResponse(json.dumps(health_status), content_type="application/json")
        return self.get_response(request)

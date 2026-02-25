"""
Core views for system-level endpoints.
"""

from django.db import connection
from django.http import JsonResponse
from django.views import View

from .models import SiteMaintenanceControl


class HealthCheckView(View):
    """
    Health check endpoint for monitoring service availability.

    Returns:
        - 200 OK: Service is healthy
        - 503 Service Unavailable: Service is unhealthy or in maintenance mode
    """

    def get(self, request):
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
            return JsonResponse(health_status, status=503)

        # Check maintenance mode
        try:
            config = SiteMaintenanceControl.load()
            if config.is_maintenance:
                health_status["status"] = "maintenance"
                health_status["maintenance"] = True
                health_status["maintenance_message"] = config.message
                return JsonResponse(health_status, status=503)
        except Exception:
            # If we can't read maintenance config, don't block the site
            pass

        return JsonResponse(health_status, status=200)

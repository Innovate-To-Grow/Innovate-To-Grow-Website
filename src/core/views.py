"""
Core views for system-level endpoints.
"""

from django.http import JsonResponse
from django.db import connection
from django.views import View


class HealthCheckView(View):
    """
    Health check endpoint for monitoring service availability.
    
    Returns:
        - 200 OK: Service is healthy
        - 503 Service Unavailable: Service is unhealthy
    """
    
    def get(self, request):
        health_status = {
            "status": "ok",
            "database": "ok",
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
        
        return JsonResponse(health_status, status=200)


from django.http import HttpResponse


class HealthCheckMiddleware:
    """Allow ALB health checks to bypass ALLOWED_HOSTS."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            # Import here to avoid circular imports
            from django.db import connection

            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                return HttpResponse('{"status":"ok"}', content_type="application/json")
            except Exception:
                return HttpResponse('{"status":"error"}', content_type="application/json", status=503)
        return self.get_response(request)

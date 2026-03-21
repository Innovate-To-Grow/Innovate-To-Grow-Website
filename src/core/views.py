"""
Core views for system-level endpoints.
"""

from django.shortcuts import render
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import SiteMaintenanceControl


class MaintenanceBypassView(APIView):
    """Verify a bypass password to skip maintenance mode."""

    permission_classes = [AllowAny]

    def post(self, request):
        password = request.data.get("password", "")
        if not password:
            return Response({"success": False, "error": "Password is required."}, status=status.HTTP_400_BAD_REQUEST)

        config = SiteMaintenanceControl.load()

        if not config.is_maintenance:
            return Response(
                {"success": False, "error": "Maintenance mode is not active."}, status=status.HTTP_400_BAD_REQUEST
            )

        if not config.bypass_password:
            return Response(
                {"success": False, "error": "Bypass is not configured."}, status=status.HTTP_400_BAD_REQUEST
            )

        if password == config.bypass_password:
            return Response({"success": True})

        return Response({"success": False, "error": "Incorrect password."}, status=status.HTTP_403_FORBIDDEN)


def custom_404(request, exception):
    """Custom 404 page using the admin theme."""
    return render(request, "404.html", status=404)

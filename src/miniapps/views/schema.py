from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from miniapps.models import MiniApp
from miniapps.serializers import MiniAppDataSchemaSerializer


class MiniAppSchemaView(APIView):
    """Read-only schema endpoint for the iframe SDK."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, app_slug):
        app = get_object_or_404(MiniApp, slug=app_slug, status="published")
        schema = getattr(app, "data_schema", None)
        if not schema:
            return Response({"fields": []})
        serializer = MiniAppDataSchemaSerializer(schema)
        return Response(serializer.data)

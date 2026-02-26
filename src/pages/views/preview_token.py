"""Views for the PagePreviewToken API (shareable preview links)."""

import logging

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import HomePage, Page, PagePreviewToken
from ..serializers.preview_token import (
    PreviewTokenCreateSerializer,
    PreviewTokenResponseSerializer,
)
from ..serializers.serializers import HomePageSerializer, PageSerializer

logger = logging.getLogger(__name__)


class CreatePreviewTokenView(APIView):
    """Create a new shareable preview token for a page."""

    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        serializer = PreviewTokenCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        token = serializer.save()
        response_serializer = PreviewTokenResponseSerializer(token, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ListPreviewTokensView(APIView):
    """List active preview tokens for a specific page."""

    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        object_id = request.query_params.get("object_id")
        content_type_label = request.query_params.get("content_type", "page")

        if not object_id:
            return Response({"detail": "object_id required"}, status=status.HTTP_400_BAD_REQUEST)

        model_class = HomePage if content_type_label == "homepage" else Page
        ct = ContentType.objects.get_for_model(model_class)

        tokens = PagePreviewToken.objects.filter(
            content_type=ct,
            object_id=object_id,
            is_active=True,
            expires_at__gt=timezone.now(),
        )
        serializer = PreviewTokenResponseSerializer(tokens, many=True, context={"request": request})
        return Response({"tokens": serializer.data})


class RevokePreviewTokenView(APIView):
    """Revoke (deactivate) a preview token."""

    permission_classes = [IsAdminUser]

    def post(self, request, token, *args, **kwargs):
        try:
            preview_token = PagePreviewToken.objects.get(token=token)
        except PagePreviewToken.DoesNotExist:
            return Response({"detail": "Token not found"}, status=status.HTTP_404_NOT_FOUND)

        preview_token.revoke()
        return Response({"detail": "Token revoked"})


class PreviewByTokenView(APIView):
    """
    Public endpoint: retrieve page data using a preview token.

    Anyone with a valid token can view the page content — no authentication required.
    """

    permission_classes = [AllowAny]

    def get(self, request, token, *args, **kwargs):
        try:
            preview_token = PagePreviewToken.objects.get(token=token)
        except PagePreviewToken.DoesNotExist:
            return Response({"detail": "Preview link not found"}, status=status.HTTP_404_NOT_FOUND)

        if not preview_token.is_valid:
            return Response({"detail": "Preview link has expired or been revoked"}, status=status.HTTP_410_GONE)

        # Get the actual page/homepage object
        obj = preview_token.content_object
        if obj is None:
            return Response({"detail": "Page not found"}, status=status.HTTP_404_NOT_FOUND)

        # Serialize based on content type
        if isinstance(obj, HomePage):
            serializer = HomePageSerializer(obj)
        else:
            serializer = PageSerializer(obj)

        data = serializer.data
        data["is_preview"] = True
        return Response(data)

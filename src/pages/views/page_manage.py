"""
Page management API views (admin-only CRUD).

Provides endpoints for the GrapesJS editor to load and save page data.
"""

import logging

from rest_framework import status
from rest_framework.generics import (
    CreateAPIView,
    ListAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import HomePage, Page
from ..serializers.page_manage import (
    HomePageManageDetailSerializer,
    HomePageManageListSerializer,
    HomePageManageWriteSerializer,
    PageManageDetailSerializer,
    PageManageListSerializer,
    PageManageWriteSerializer,
)

logger = logging.getLogger(__name__)


# ========================
# Page Management
# ========================


class PageManageListCreateView(ListAPIView, CreateAPIView):
    """List all pages or create a new page (admin only)."""

    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PageManageWriteSerializer
        return PageManageListSerializer

    def get_queryset(self):
        return Page.objects.all().order_by("-updated_at")

    def perform_create(self, serializer):
        page = serializer.save()
        if self.request.user.is_authenticated:
            page.created_by = self.request.user
            page.updated_by = self.request.user
            page.save(update_fields=["created_by", "updated_by"])


class PageManageDetailView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a page (admin only)."""

    permission_classes = [IsAdminUser]
    queryset = Page.objects.all()

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return PageManageWriteSerializer
        return PageManageDetailSerializer

    def perform_update(self, serializer):
        page = serializer.save()
        if self.request.user.is_authenticated:
            page.updated_by = self.request.user
            page.save(update_fields=["updated_by"])
            page.save_version(comment=f"Saved via editor by {self.request.user}", user=self.request.user)


class PageManagePublishView(APIView):
    """Toggle publish/unpublish for a page (admin only)."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            page = Page.objects.get(pk=pk)
        except Page.DoesNotExist:
            return Response({"detail": "Page not found."}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get("action", "publish")
        try:
            if action == "publish":
                page.publish(user=request.user)
            elif action == "unpublish":
                page.unpublish(user=request.user)
            elif action == "submit_for_review":
                page.submit_for_review(user=request.user)
            else:
                return Response({"detail": f"Unknown action: {action}"}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"status": page.status})


# ========================
# HomePage Management
# ========================


class HomePageManageListCreateView(ListAPIView, CreateAPIView):
    """List all home pages or create a new one (admin only)."""

    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return HomePageManageWriteSerializer
        return HomePageManageListSerializer

    def get_queryset(self):
        return HomePage.objects.all().order_by("-updated_at")


class HomePageManageDetailView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a home page (admin only)."""

    permission_classes = [IsAdminUser]
    queryset = HomePage.objects.all()

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return HomePageManageWriteSerializer
        return HomePageManageDetailSerializer

    def perform_update(self, serializer):
        homepage = serializer.save()
        if self.request.user.is_authenticated:
            homepage.save_version(comment=f"Saved via editor by {self.request.user}", user=self.request.user)


class HomePageManagePublishView(APIView):
    """Toggle publish/unpublish for a home page (admin only)."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            homepage = HomePage.objects.get(pk=pk)
        except HomePage.DoesNotExist:
            return Response({"detail": "Home page not found."}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get("action", "publish")
        try:
            if action == "publish":
                homepage.publish(user=request.user)
            elif action == "unpublish":
                homepage.unpublish(user=request.user)
            elif action == "activate":
                homepage.is_active = True
                homepage.save(update_fields=["is_active"])
            elif action == "deactivate":
                homepage.is_active = False
                homepage.save(update_fields=["is_active"])
            else:
                return Response({"detail": f"Unknown action: {action}"}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, Exception) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"status": homepage.status, "is_active": homepage.is_active})

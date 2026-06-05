from rest_framework import status
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from ..models import PastProjectShare
from ..serializers import PastProjectShareListSerializer, PastProjectShareSerializer
from ..throttles import PastProjectShareRateThrottle


class PastProjectShareCreateAPIView(CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PastProjectShareSerializer
    throttle_classes = [PastProjectShareRateThrottle]


class PastProjectShareMineAPIView(ListAPIView):
    """List the shares created by the current user (newest first)."""

    permission_classes = [IsAuthenticated]
    serializer_class = PastProjectShareListSerializer

    def get_queryset(self):
        return PastProjectShare.objects.filter(created_by=self.request.user)


class PastProjectShareDetailAPIView(RetrieveUpdateDestroyAPIView):
    serializer_class = PastProjectShareSerializer
    queryset = PastProjectShare.objects.all()
    lookup_field = "pk"

    def get_permissions(self):
        # Viewing a shared snapshot is public; changing one requires authentication.
        if self.request.method in {"DELETE", "PATCH", "PUT"}:
            return [IsAuthenticated()]
        return [AllowAny()]

    def update(self, request, *args, **kwargs):
        # Re-filter by owner (not get_object) so a non-owner gets 404, not 403,
        # and existence is not leaked. Mirrors the delete path below.
        instance = PastProjectShare.objects.filter(pk=kwargs["pk"], created_by=request.user).first()
        if instance is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        # Re-filter by owner (not get_object) so a non-owner gets 404, not 403,
        # and existence is not leaked. Mirrors the contact-email owner pattern.
        instance = PastProjectShare.objects.filter(pk=kwargs["pk"], created_by=request.user).first()
        if instance is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

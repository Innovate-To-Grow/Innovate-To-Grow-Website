"""Views for the SavedComponent API (reusable component library)."""

from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveDestroyAPIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from ..models import SavedComponent
from ..serializers.saved_component import SavedComponentSerializer


class SavedComponentListCreateView(ListCreateAPIView):
    """List all saved components or create a new one."""

    serializer_class = SavedComponentSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = SavedComponent.objects.all()
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({"components": serializer.data})


class SavedComponentDetailView(RetrieveDestroyAPIView):
    """Retrieve or delete a saved component."""

    serializer_class = SavedComponentSerializer
    permission_classes = [IsAdminUser]
    queryset = SavedComponent.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

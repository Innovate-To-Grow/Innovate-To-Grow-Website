from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from ..models import Menu, FooterContent
from ..serializers import MenuSerializer, FooterContentSerializer


class MenuAPIView(ListAPIView):
    """
    Retrieve menu structure.
    Returns Menu objects with their linked Pages.
    """
    serializer_class = MenuSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        """Return all menus."""
        return Menu.objects.all().order_by('display_name')
    
    def list(self, request, *args, **kwargs):
        """Override to return custom response format."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'menus': serializer.data
        })


class FooterContentAPIView(APIView):
    """
    Retrieve the currently active footer content.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        footer = FooterContent.get_active()
        if not footer:
            return Response(
                {"detail": "No active footer content found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = FooterContentSerializer(footer)
        return Response(serializer.data)

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from ..models import Menu, FooterContent
from ..serializers import MenuSerializer, FooterContentSerializer


class LayoutAPIView(APIView):
    """
    Unified endpoint for layout data (menus and footer).
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        # 1. Get menus
        menus = Menu.objects.all().order_by('display_name')
        menu_serializer = MenuSerializer(menus, many=True)
        
        # 2. Get active footer
        footer = FooterContent.get_active()
        footer_data = None
        if footer:
            footer_serializer = FooterContentSerializer(footer)
            footer_data = footer_serializer.data
            
        return Response({
            'menus': menu_serializer.data,
            'footer': footer_data
        })

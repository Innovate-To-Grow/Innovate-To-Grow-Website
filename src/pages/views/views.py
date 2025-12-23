from django.views.generic import TemplateView
from rest_framework.generics import RetrieveAPIView, ListAPIView
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from ..models import Page, HomePage
from ..serializers import PageSerializer, HomePageSerializer


class PreviewPopupView(TemplateView):
    """
    Render the popup preview page for live editing.
    """
    template_name = 'pages/preview_popup.html'


class HomePageAPIView(APIView):
    """
    Retrieve the currently active home page.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        home_page = HomePage.get_active()
        if not home_page:
            return Response(
                {"detail": "No active home page found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = HomePageSerializer(home_page)
        return Response(serializer.data)


class PageListAPIView(ListAPIView):
    """
    List all pages (for menu editor dropdown).
    """
    serializer_class = PageSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Page.objects.all().order_by('title')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        # Return simplified list for menu editor
        pages = [{'slug': p.slug, 'title': p.title, 'page_type': p.page_type} for p in queryset]
        return Response({'pages': pages})


class PageRetrieveAPIView(RetrieveAPIView):
    """
    Retrieve a page by slug.
    """
    queryset = Page.objects.all()
    serializer_class = PageSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    permission_classes = [AllowAny]

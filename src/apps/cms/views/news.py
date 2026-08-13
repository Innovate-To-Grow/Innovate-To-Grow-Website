from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from apps.cms.models import NewsArticle
from apps.cms.serializers import NewsArticleDetailSerializer, NewsArticleSerializer
from apps.core.utils.http_cache import public_json_response


class NewsPageNumberPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 50


class NewsListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NewsArticleSerializer
    queryset = NewsArticle.objects.all()
    pagination_class = NewsPageNumberPagination

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return public_json_response(request, response.data)


class NewsDetailAPIView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = NewsArticleDetailSerializer
    queryset = NewsArticle.objects.all()
    lookup_field = "pk"

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return public_json_response(request, response.data)

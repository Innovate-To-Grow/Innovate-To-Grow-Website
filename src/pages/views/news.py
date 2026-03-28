from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from pages.models import NewsArticle
from pages.serializers import NewsArticleDetailSerializer, NewsArticleSerializer


class NewsPageNumberPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 50


class NewsListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NewsArticleSerializer
    queryset = NewsArticle.objects.all()
    pagination_class = NewsPageNumberPagination


class NewsDetailAPIView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = NewsArticleDetailSerializer
    queryset = NewsArticle.objects.all()
    lookup_field = "pk"

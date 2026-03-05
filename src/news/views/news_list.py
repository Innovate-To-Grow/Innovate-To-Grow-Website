from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from ..models import NewsArticle
from ..pagination import NewsPageNumberPagination
from ..serializers import NewsArticleSerializer


class NewsListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NewsArticleSerializer
    queryset = NewsArticle.objects.all()
    pagination_class = NewsPageNumberPagination

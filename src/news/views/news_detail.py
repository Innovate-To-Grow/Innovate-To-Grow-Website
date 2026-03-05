from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from ..models import NewsArticle
from ..serializers import NewsArticleDetailSerializer


class NewsDetailAPIView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = NewsArticleDetailSerializer
    queryset = NewsArticle.objects.all()
    lookup_field = "pk"

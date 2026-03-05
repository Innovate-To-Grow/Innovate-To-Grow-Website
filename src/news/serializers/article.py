from rest_framework import serializers

from ..models import NewsArticle


class NewsArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsArticle
        fields = ["id", "title", "source_url", "summary", "image_url", "published_at"]

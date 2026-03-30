from rest_framework import serializers

from cms.models import NewsArticle


class NewsArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsArticle
        fields = ["id", "title", "source_url", "summary", "image_url", "published_at"]


class NewsArticleDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsArticle
        fields = [
            "id",
            "title",
            "source_url",
            "summary",
            "image_url",
            "author",
            "published_at",
            "content",
            "hero_image_url",
            "hero_caption",
        ]

from rest_framework import serializers
from ..models import Page, HomePage


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = [
            "id",
            "title",
            "slug",
            "page_type",
            "page_body",
            "external_url",
            "meta_title",
            "meta_description",
            "meta_keywords",
            "og_image",
            "canonical_url",
            "meta_robots",
            "template_name",
            "published",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class HomePageSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomePage
        fields = ["id", "name", "body", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

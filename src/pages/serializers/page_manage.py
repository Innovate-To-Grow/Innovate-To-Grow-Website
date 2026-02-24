"""
Serializers for the page management API (admin CRUD).

These serializers handle reading and writing GrapesJS editor data
for Page and HomePage models.
"""

from rest_framework import serializers

from ..models import HomePage, Page


class PageManageListSerializer(serializers.ModelSerializer):
    """Compact serializer for listing pages in admin."""

    class Meta:
        model = Page
        fields = ["id", "title", "slug", "status", "updated_at", "created_at"]
        read_only_fields = fields


class PageManageDetailSerializer(serializers.ModelSerializer):
    """Full serializer for page editor (includes grapesjs_json)."""

    class Meta:
        model = Page
        fields = [
            "id",
            "title",
            "slug",
            "template_name",
            "html",
            "css",
            "grapesjs_json",
            "dynamic_config",
            "meta_title",
            "meta_description",
            "meta_keywords",
            "og_image",
            "canonical_url",
            "meta_robots",
            "google_site_verification",
            "google_structured_data",
            "status",
            "updated_at",
            "created_at",
        ]
        read_only_fields = ["id", "status", "updated_at", "created_at"]


class PageManageWriteSerializer(serializers.ModelSerializer):
    """Serializer for saving page data from the GrapesJS editor."""

    class Meta:
        model = Page
        fields = [
            "title",
            "slug",
            "template_name",
            "html",
            "css",
            "grapesjs_json",
            "dynamic_config",
            "meta_title",
            "meta_description",
            "meta_keywords",
            "og_image",
            "canonical_url",
            "meta_robots",
            "google_site_verification",
            "google_structured_data",
        ]

    def validate_slug(self, value):
        """Ensure slug uniqueness on create (update skips this)."""
        if self.instance is None:
            if Page.objects.filter(slug=value).exists():
                raise serializers.ValidationError(f"A page with slug '{value}' already exists.")
        return value


class HomePageManageListSerializer(serializers.ModelSerializer):
    """Compact serializer for listing home pages in admin."""

    class Meta:
        model = HomePage
        fields = ["id", "name", "is_active", "status", "updated_at", "created_at"]
        read_only_fields = fields


class HomePageManageDetailSerializer(serializers.ModelSerializer):
    """Full serializer for home page editor (includes grapesjs_json)."""

    class Meta:
        model = HomePage
        fields = [
            "id",
            "name",
            "is_active",
            "html",
            "css",
            "grapesjs_json",
            "dynamic_config",
            "status",
            "updated_at",
            "created_at",
        ]
        read_only_fields = ["id", "is_active", "status", "updated_at", "created_at"]


class HomePageManageWriteSerializer(serializers.ModelSerializer):
    """Serializer for saving home page data from the GrapesJS editor."""

    class Meta:
        model = HomePage
        fields = [
            "name",
            "html",
            "css",
            "grapesjs_json",
            "dynamic_config",
        ]

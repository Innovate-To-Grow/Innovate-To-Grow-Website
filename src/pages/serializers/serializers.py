from rest_framework import serializers

from ..models import (
    FooterContent,
    HomePage,
    Menu,
    MenuPageLink,
    Page,
)


class PageSerializer(serializers.ModelSerializer):
    published = serializers.BooleanField(read_only=True)  # computed from status

    class Meta:
        model = Page
        fields = [
            "id",
            "title",
            "slug",
            "html",
            "css",
            "dynamic_config",
            "meta_title",
            "meta_description",
            "meta_keywords",
            "og_image",
            "canonical_url",
            "meta_robots",
            "template_name",
            "status",
            "published",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at", "published"]


class HomePageSerializer(serializers.ModelSerializer):
    published = serializers.BooleanField(read_only=True)  # computed from status

    class Meta:
        model = HomePage
        fields = [
            "id",
            "name",
            "is_active",
            "html",
            "css",
            "dynamic_config",
            "status",
            "published",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "published"]


class MenuSerializer(serializers.ModelSerializer):
    """Serializer for Menu with JSON items."""

    items = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ["id", "name", "display_name", "description", "items", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_items(self, obj):
        """Process menu items with dynamic data injection."""
        raw_items = obj.items or []
        return self._process_items(raw_items)

    def _process_items(self, items):
        """Recursively process menu items."""
        processed = []
        for item in items:
            processed_item = {
                "type": item.get("type", "page"),
                "title": item.get("title", ""),
                "icon": item.get("icon", ""),
                "open_in_new_tab": item.get("open_in_new_tab", False),
            }

            if item.get("type") == "home":
                home_page = HomePage.get_active()
                processed_item["url"] = "/"
                processed_item["page_type"] = "home"
                if home_page:
                    processed_item["home_active"] = True
                    processed_item["home_name"] = home_page.name
                else:
                    processed_item["home_active"] = False

            elif item.get("type") == "page":
                page_slug = item.get("page_slug", "")
                processed_item["page_slug"] = page_slug
                processed_item["url"] = f"/pages/{page_slug}" if page_slug else "#"
                processed_item["page_type"] = "page"

                if not processed_item["title"] and page_slug:
                    try:
                        page = Page.objects.get(slug=page_slug)
                        processed_item["title"] = page.title
                    except Page.DoesNotExist:
                        pass

            elif item.get("type") == "external":
                processed_item["url"] = item.get("url", "#")
                processed_item["page_type"] = "external"

            children = item.get("children", [])
            if children:
                processed_item["children"] = self._process_items(children)
            else:
                processed_item["children"] = []

            processed.append(processed_item)

        return processed


class FooterContentSerializer(serializers.ModelSerializer):
    """Serializer for FooterContent structured JSON."""

    class Meta:
        model = FooterContent
        fields = [
            "id",
            "name",
            "slug",
            "content",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class MenuPageLinkSerializer(serializers.ModelSerializer):
    """Serializer for the legacy Menu-Page link objects."""

    class Meta:
        model = MenuPageLink
        fields = [
            "id",
            "menu",
            "page",
            "order",
            "custom_title",
            "css_classes",
            "icon",
            "open_in_new_tab",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

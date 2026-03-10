from rest_framework import serializers

from ..models import (
    FooterContent,
    Menu,
)


class MenuSerializer(serializers.ModelSerializer):
    """Serializer for Menu with JSON items."""

    items = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ["id", "name", "display_name", "description", "items", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_items(self, obj):
        """Process menu items."""
        raw_items = obj.items or []
        return self._process_items(raw_items)

    def _process_items(self, items):
        """Recursively process menu items."""
        processed = []
        for item in items:
            processed_item = {
                "type": item.get("type", "app"),
                "title": item.get("title", ""),
                "icon": item.get("icon", ""),
                "open_in_new_tab": item.get("open_in_new_tab", False),
            }

            if item.get("type") == "external":
                processed_item["url"] = item.get("url", "#")

            elif item.get("type") == "app":
                processed_item["url"] = item.get("url", "#")

            else:
                # Fallback for any unrecognized type
                processed_item["url"] = item.get("url", "#")

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

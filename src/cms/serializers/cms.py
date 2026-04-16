from rest_framework import serializers

from cms.models import CMSBlock, CMSPage
from cms.services.sanitize import sanitize_html


def _sanitize_block_data(data):
    """Recursively sanitize all *_html values in a block's JSON data."""
    if isinstance(data, dict):
        return {
            k: (sanitize_html(v) if isinstance(v, str) and k.endswith("_html") else _sanitize_block_data(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_sanitize_block_data(item) for item in data]
    return data


class CMSBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = CMSBlock
        fields = ["block_type", "sort_order", "data"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get("data"):
            data["data"] = _sanitize_block_data(data["data"])
        return data


class CMSPageSerializer(serializers.ModelSerializer):
    blocks = serializers.SerializerMethodField()

    class Meta:
        model = CMSPage
        fields = ["slug", "route", "title", "page_css_class", "page_css", "meta_description", "blocks"]

    # noinspection PyMethodMayBeStatic
    def get_blocks(self, obj):
        blocks = obj.blocks.all().order_by("sort_order")
        return CMSBlockSerializer(blocks, many=True).data

from rest_framework import serializers

from apps.cms.models import CMSBlock, CMSPage
from apps.cms.services.sanitization.sanitize import sanitize_block_data


class CMSBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = CMSBlock
        fields = ["block_type", "sort_order", "data"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get("data"):
            data["data"] = sanitize_block_data(data["data"])
        return data


class CMSPageSerializer(serializers.ModelSerializer):
    blocks = serializers.SerializerMethodField()

    class Meta:
        model = CMSPage
        fields = ["slug", "route", "title", "page_css_class", "meta_description", "blocks"]

    # noinspection PyMethodMayBeStatic
    def get_blocks(self, obj):
        # CMSBlock.Meta.ordering is ["sort_order"], so .all() preserves order while
        # reusing the view's prefetch_related("blocks") cache; an explicit .order_by()
        # would re-query and defeat the prefetch.
        blocks = obj.blocks.all()
        return CMSBlockSerializer(blocks, many=True).data

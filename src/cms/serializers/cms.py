from rest_framework import serializers

from cms.models import CMSBlock, CMSPage


class CMSBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = CMSBlock
        fields = ["block_type", "sort_order", "data"]


class CMSPageSerializer(serializers.ModelSerializer):
    blocks = serializers.SerializerMethodField()

    class Meta:
        model = CMSPage
        fields = ["slug", "route", "title", "page_css_class", "meta_description", "blocks"]

    # noinspection PyMethodMayBeStatic
    def get_blocks(self, obj):
        blocks = obj.blocks.all().order_by("sort_order")
        return CMSBlockSerializer(blocks, many=True).data

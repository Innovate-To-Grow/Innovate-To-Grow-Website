from rest_framework import serializers

from cms.models import PageView


class PageViewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageView
        fields = ["path", "referrer"]

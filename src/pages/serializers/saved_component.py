"""Serializers for the SavedComponent model (reusable component library)."""

from rest_framework import serializers

from ..models import SavedComponent


class SavedComponentSerializer(serializers.ModelSerializer):
    """Serializer for listing and creating saved components."""

    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SavedComponent
        fields = [
            "id",
            "name",
            "category",
            "grapesjs_data",
            "html",
            "css",
            "created_by",
            "created_by_name",
            "created_at",
            "is_shared",
        ]
        read_only_fields = ["id", "created_by", "created_by_name", "created_at"]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return str(obj.created_by)
        return None

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)

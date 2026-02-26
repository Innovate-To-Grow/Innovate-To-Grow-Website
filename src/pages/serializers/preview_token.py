"""Serializers for the PagePreviewToken model (shareable preview links)."""

from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework import serializers

from ..models import HomePage, Page, PagePreviewToken


class PreviewTokenCreateSerializer(serializers.Serializer):
    """Serializer for creating a new preview token."""

    object_id = serializers.UUIDField()
    content_type = serializers.ChoiceField(choices=["page", "homepage"])
    expires_in_hours = serializers.IntegerField(default=168, min_value=1, max_value=720)
    note = serializers.CharField(max_length=255, required=False, default="")

    def validate(self, attrs):
        ct_label = attrs["content_type"]
        object_id = attrs["object_id"]

        if ct_label == "page":
            model_class = Page
        else:
            model_class = HomePage

        # Verify the object exists
        if not model_class.objects.filter(id=object_id).exists():
            raise serializers.ValidationError(f"{ct_label.title()} with id {object_id} not found.")

        attrs["model_class"] = model_class
        return attrs

    def create(self, validated_data):
        model_class = validated_data.pop("model_class")
        ct = ContentType.objects.get_for_model(model_class)
        expires_at = timezone.now() + timedelta(hours=validated_data["expires_in_hours"])

        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        token = PagePreviewToken(
            content_type=ct,
            object_id=validated_data["object_id"],
            created_by=user,
            expires_at=expires_at,
            note=validated_data.get("note", ""),
        )
        token.save()
        return token


class PreviewTokenResponseSerializer(serializers.ModelSerializer):
    """Serializer for returning preview token data."""

    preview_url = serializers.SerializerMethodField()

    class Meta:
        model = PagePreviewToken
        fields = ["id", "token", "preview_url", "expires_at", "note", "created_at", "is_active"]
        read_only_fields = fields

    def get_preview_url(self, obj):
        frontend_url = getattr(settings, "FRONTEND_URL", "")
        if frontend_url:
            return f"{frontend_url.rstrip('/')}/preview/{obj.token}"
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(f"/preview/{obj.token}")
        return f"/preview/{obj.token}"

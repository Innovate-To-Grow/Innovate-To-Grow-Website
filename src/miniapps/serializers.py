from rest_framework import serializers

from .models import MiniApp, MiniAppDataRecord, MiniAppDataSchema


class MiniAppListSerializer(serializers.ModelSerializer):
    class Meta:
        model = MiniApp
        fields = ["id", "title", "slug", "url_path", "description", "icon", "embeddable", "status"]


class MiniAppDataSchemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = MiniAppDataSchema
        fields = ["id", "fields", "updated_at"]


class MiniAppDataRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MiniAppDataRecord
        fields = ["id", "data", "created_by", "created_at", "updated_at"]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

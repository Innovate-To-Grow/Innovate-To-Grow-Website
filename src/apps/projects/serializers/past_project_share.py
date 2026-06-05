from rest_framework import serializers

from ..models import PastProjectShare


class PastProjectShareRowSerializer(serializers.Serializer):
    semester_label = serializers.CharField(max_length=50, allow_blank=True)
    class_code = serializers.CharField(max_length=20, allow_blank=True)
    team_number = serializers.CharField(max_length=20, allow_blank=True)
    team_name = serializers.CharField(max_length=255, allow_blank=True)
    project_title = serializers.CharField(max_length=500)
    organization = serializers.CharField(max_length=255, allow_blank=True)
    industry = serializers.CharField(max_length=100, allow_blank=True)
    abstract = serializers.CharField(allow_blank=True)
    student_names = serializers.CharField(allow_blank=True)


class PastProjectShareSerializer(serializers.ModelSerializer):
    rows = PastProjectShareRowSerializer(many=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    share_url = serializers.SerializerMethodField()

    class Meta:
        model = PastProjectShare
        fields = ["id", "rows", "note", "share_url", "created_at"]
        read_only_fields = ["id", "share_url", "created_at"]

    # noinspection PyMethodMayBeStatic
    def validate_rows(self, value):
        if not value:
            raise serializers.ValidationError("At least one row is required.")
        if len(value) > 1000:
            raise serializers.ValidationError("At most 1000 rows may be shared.")
        return value

    def get_share_url(self, obj):
        request = self.context.get("request")
        if request is None:
            return f"/past-projects/{obj.pk}"
        return request.build_absolute_uri(f"/past-projects/{obj.pk}")

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        created_by = user if (user is not None and user.is_authenticated) else None
        return PastProjectShare.objects.create(
            rows=validated_data["rows"],
            note=validated_data.get("note", ""),
            created_by=created_by,
        )

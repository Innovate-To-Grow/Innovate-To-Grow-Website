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
    name = serializers.CharField(required=True, allow_blank=False, max_length=200)
    rows = PastProjectShareRowSerializer(many=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    share_url = serializers.SerializerMethodField()

    class Meta:
        model = PastProjectShare
        fields = ["id", "name", "rows", "note", "share_url", "created_at"]
        read_only_fields = ["id", "share_url", "created_at"]

    # name uses DRF CharField defaults (allow_blank=False + trim_whitespace=True), so
    # empty/whitespace-only names are rejected and the stored value is auto-trimmed —
    # no custom validate_name needed.

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
            name=validated_data["name"],
            rows=validated_data["rows"],
            note=validated_data.get("note", ""),
            created_by=created_by,
        )


class PastProjectShareListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the account "my shares" list (omits the rows payload)."""

    share_url = serializers.SerializerMethodField()
    row_count = serializers.SerializerMethodField()

    class Meta:
        model = PastProjectShare
        fields = ["id", "name", "note", "share_url", "row_count", "created_at"]

    def get_share_url(self, obj):
        request = self.context.get("request")
        if request is None:
            return f"/past-projects/{obj.pk}"
        return request.build_absolute_uri(f"/past-projects/{obj.pk}")

    # noinspection PyMethodMayBeStatic
    def get_row_count(self, obj):
        return len(obj.rows or [])

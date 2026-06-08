from django.conf import settings
from rest_framework import serializers

from ..models import PastProjectShare


def _share_url(obj, request):
    """Build the public share URL on the *frontend* origin.

    The share page (`/past-projects/<id>`) is a React SPA route served by the
    frontend, not Django. Using ``request.build_absolute_uri`` here would point
    at the API host (e.g. ``api.i2g.ucmerced.edu``), whose catch-all returns the
    admin 404 page — so prefer ``FRONTEND_URL`` like the rest of the codebase,
    and only fall back to the request origin (dev/same-origin) when it is unset.
    """
    base = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    if base:
        return f"{base}/past-projects/{obj.pk}"
    if request is not None:
        return request.build_absolute_uri(f"/past-projects/{obj.pk}")
    return f"/past-projects/{obj.pk}"


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
    # Round-trip the frontend's presenting flag ('Yes'/'No'/'') so stored rows match freshly
    # searched rows — the client dedup fingerprint includes is_presenting, and dropping it here
    # made an owner's "add rows" re-add a project already in the share. Optional + default so
    # pre-existing shares (saved without the field) keep validating and serialize as "".
    is_presenting = serializers.CharField(max_length=10, allow_blank=True, required=False, default="")


class PastProjectShareSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=True, allow_blank=False, max_length=200)
    rows = PastProjectShareRowSerializer(many=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    details_text = serializers.CharField(required=False, allow_blank=True, default="")
    share_url = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = PastProjectShare
        fields = ["id", "name", "rows", "note", "details_text", "share_url", "can_edit", "created_at"]
        read_only_fields = ["id", "share_url", "can_edit", "created_at"]

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
        return _share_url(obj, self.context.get("request"))

    def get_can_edit(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(user is not None and user.is_authenticated and obj.created_by_id == user.pk)

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        created_by = user if (user is not None and user.is_authenticated) else None
        return PastProjectShare.objects.create(
            name=validated_data["name"],
            rows=validated_data["rows"],
            note=validated_data.get("note", ""),
            details_text=validated_data.get("details_text", ""),
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
        return _share_url(obj, self.context.get("request"))

    # noinspection PyMethodMayBeStatic
    def get_row_count(self, obj):
        return len(obj.rows or [])

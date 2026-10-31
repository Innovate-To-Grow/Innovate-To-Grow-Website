import uuid

import bleach
from django.conf import settings
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from ..models import PastProjectShare
from ..services.share_names import default_share_name
from ..services.share_rows import UnknownShareRows, rebuild_share_rows, rows_for_display

# Allowlist for a share's stored rich text (the note): inline emphasis + line/paragraph structure, no
# attributes. Defense-in-depth so safety does not rely solely on every client render calling
# DOMPurify.
DETAILS_ALLOWED_TAGS = ["br", "div", "p", "b", "strong", "i", "em", "u", "mark", "a"]
DETAILS_ALLOWED_ATTRIBUTES = {
    "a": ["href"],
    # data-past-project-key tags each inserted project so a re-insert can append only new projects;
    # it must survive sanitize. Kept in sync with the frontend RICH_DETAIL_ALLOWED_ATTR.
    "div": ["data-past-project-note-curation", "data-past-project-key"],
}

# The share-level note is rich text (HTML). Cap well above plain-text length so emphasis tags
# don't reject a reasonable note.
NOTE_MAX_LENGTH = 50_000

# Row text is rebuilt from the catalog, so these caps only bound a request: about ten times the longest archive
# abstract (~2,000 characters) and student list (~140).
ROW_ABSTRACT_MAX_LENGTH = 20_000
ROW_STUDENT_NAMES_MAX_LENGTH = 5_000
MAX_SHARE_ROWS = 1000
# Rows across all of one member's shares: about five copies of the whole archive. Each row is a catalog copy of up
# to ~2 KB, so this bounds what one account stores at about 10 MB (100 full shares would be ~200 MB).
MAX_MEMBER_SHARE_ROWS = 5000


class StalePastProjectShareSnapshot(Exception):
    """Raised when an optimistic shared-project update loses its version race."""


def sanitize_details_text(value: str) -> str:
    """Strip any markup outside the rich-detail allowlist from a share's rich text."""
    if not value:
        return value
    return bleach.clean(value, tags=DETAILS_ALLOWED_TAGS, attributes=DETAILS_ALLOWED_ATTRIBUTES, strip=True)


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
    id = serializers.CharField(max_length=36, required=False)
    semester_label = serializers.CharField(max_length=50, allow_blank=True)
    class_code = serializers.CharField(max_length=20, allow_blank=True)
    team_number = serializers.CharField(max_length=20, allow_blank=True)
    team_name = serializers.CharField(max_length=255, allow_blank=True)
    project_title = serializers.CharField(max_length=500)
    organization = serializers.CharField(max_length=255, allow_blank=True)
    industry = serializers.CharField(max_length=100, allow_blank=True)
    abstract = serializers.CharField(allow_blank=True, max_length=ROW_ABSTRACT_MAX_LENGTH)
    student_names = serializers.CharField(allow_blank=True, max_length=ROW_STUDENT_NAMES_MAX_LENGTH)
    # Accepted so clients that send the presenting flag ('Yes'/'No'/'') keep validating; it is never stored as
    # sent. The row is rebuilt from the catalog (services/share_rows.py): "" for an archive project, and the
    # event's flag as "Yes"/"No" for a current-semester one.
    is_presenting = serializers.CharField(max_length=10, allow_blank=True, required=False, default="")
    # "archive" or "current": the catalog the stored row was rebuilt from. Read-only, so that a row kept as stored
    # (one that no longer resolves) still names it; rows saved before rows carried it leave it out.
    catalog = serializers.CharField(read_only=True)

    # noinspection PyMethodMayBeStatic
    def validate_id(self, value):
        try:
            return str(uuid.UUID(value))
        except (TypeError, ValueError, AttributeError):
            raise serializers.ValidationError("Enter a valid project UUID.")


class PastProjectShareSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False, allow_blank=True, default="", max_length=200)
    rows = PastProjectShareRowSerializer(many=True)
    note = serializers.CharField(
        required=False, allow_blank=True, default="", trim_whitespace=False, max_length=NOTE_MAX_LENGTH
    )
    # The combined project text clients sent before the rows became the snapshot. Shares that hold one still serve
    # it, but no client writes it any more, so it is not accepted: it was the only field without a small cap.
    details_text = serializers.CharField(read_only=True)
    share_url = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    version = serializers.IntegerField(required=False, min_value=1)

    class Meta:
        model = PastProjectShare
        fields = [
            "id",
            "name",
            "rows",
            "note",
            "details_text",
            "version",
            "share_url",
            "can_edit",
            "created_at",
        ]
        read_only_fields = ["id", "share_url", "can_edit", "created_at"]

    # name is optional: a blank/omitted name is replaced with the first line of the owner's note, else a
    # generic title for the stored rows (services.share_names.default_share_name), in create()/update(). It is
    # never a row's project title. trim_whitespace=True still trims a given name.

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["rows"] = rows_for_display(data["rows"])
        return data

    # noinspection PyMethodMayBeStatic
    def validate_note(self, value):
        # The note is rich text; sanitize on write so a stored note can never carry script or
        # disallowed markup, however a client renders it.
        return sanitize_details_text(value)

    def validate_rows(self, value):
        if not value:
            raise serializers.ValidationError("At least one row is required.")
        if len(value) > MAX_SHARE_ROWS:
            raise serializers.ValidationError(f"At most {MAX_SHARE_ROWS} rows may be shared.")
        self._check_member_row_total(len(value))
        # Store what the catalog says, never the text a client sent (services/share_rows.py).
        try:
            return rebuild_share_rows(value, stored_rows=self.instance.rows if self.instance else ())
        except UnknownShareRows as exc:
            projects = "project is" if exc.count == 1 else "projects are"
            raise serializers.ValidationError(
                f"{exc.count} {projects} not among the published projects. Remove them and save again."
            ) from exc

    def _check_member_row_total(self, row_count: int) -> None:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return
        other_shares = PastProjectShare.objects.filter(created_by=user)
        stored_count = 0
        if self.instance is not None:
            other_shares = other_shares.exclude(pk=self.instance.pk)
            stored_count = len(self.instance.rows) if isinstance(self.instance.rows, list) else 0
        # Only a write that adds rows is refused, so a member already past the bound can still edit and trim.
        if row_count > stored_count and other_shares.row_total() + row_count > MAX_MEMBER_SHARE_ROWS:
            raise serializers.ValidationError(
                f"Your shared curations can hold up to {MAX_MEMBER_SHARE_ROWS:,} projects in all. "
                "Remove some projects or delete a curation you no longer need, then save again."
            )

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
        note = validated_data.get("note", "")
        name = (validated_data.get("name") or "").strip() or default_share_name(note, validated_data["rows"])
        return PastProjectShare.objects.create(
            name=name,
            rows=validated_data["rows"],
            note=note,
            created_by=created_by,
        )

    def update(self, instance, validated_data):
        expected_version = validated_data.pop("version")
        next_note = validated_data.get("note", instance.note)
        # The rows this write stores (rebuilt by validate_rows), else the ones the share already stores.
        next_rows = validated_data.get("rows", instance.rows)
        updates = {field: validated_data[field] for field in ("rows", "note") if field in validated_data}
        if "name" in validated_data:
            name = (validated_data.get("name") or "").strip()
            updates["name"] = name or default_share_name(next_note, next_rows)
        updates.update(version=F("version") + 1, updated_at=timezone.now())
        updated = type(instance).objects.filter(pk=instance.pk, version=expected_version).update(**updates)
        if updated != 1:
            raise StalePastProjectShareSnapshot
        instance.refresh_from_db()
        return instance


class PastProjectShareListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the account "my shares" list (omits the rows payload)."""

    share_url = serializers.SerializerMethodField()
    # Counted by the database (PastProjectShare.objects.summaries()), so listing never loads the rows.
    row_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PastProjectShare
        fields = ["id", "name", "note", "version", "share_url", "row_count", "created_at", "updated_at"]

    def get_share_url(self, obj):
        return _share_url(obj, self.context.get("request"))

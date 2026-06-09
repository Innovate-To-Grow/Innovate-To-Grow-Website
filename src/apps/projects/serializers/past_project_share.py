import re
import uuid

import bleach
from django.conf import settings
from rest_framework import serializers

from ..models import PastProjectShare, Project

# Allowlist for the stored details_text HTML: inline emphasis + line/paragraph structure, no
# attributes. Defense-in-depth so safety does not rely solely on every client render calling
# DOMPurify.
DETAILS_ALLOWED_TAGS = ["br", "div", "p", "b", "strong", "i", "em", "u", "mark", "a"]
DETAILS_ALLOWED_ATTRIBUTES = {"a": ["href"], "div": ["data-past-project-note-curation"]}

# Generous cap: a generated detail for ~1000 projects with long abstracts is well under this
# (low hundreds of KB), so it never rejects a legitimate large share, but it stops absurd
# payloads. details legitimately needs much more room than the note.
DETAILS_TEXT_MAX_LENGTH = 2_000_000

# The share-level note is rich text (HTML). Cap well above plain-text length so emphasis tags
# don't reject a reasonable note, but far below the details cap.
NOTE_MAX_LENGTH = 50_000


def sanitize_details_text(value: str) -> str:
    """Strip any markup outside the rich-detail allowlist from a share's details_text."""
    if not value:
        return value
    return bleach.clean(value, tags=DETAILS_ALLOWED_TAGS, attributes=DETAILS_ALLOWED_ATTRIBUTES, strip=True)


def _normalized_text_key(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _semester_label_key(value):
    label = (value or "").strip()
    if not label:
        return None

    match = re.fullmatch(r"(\d{4})(?:-\d+)?\s+(.+)", label)
    if not match:
        return None

    year, season_name = match.groups()
    normalized_season = _normalized_text_key(season_name)
    if not normalized_season:
        return None
    return year, normalized_season


def _share_row_stable_key(row):
    semester_label = (row.get("semester_label") or "").strip()
    class_code = (row.get("class_code") or "").strip()
    team_number = (row.get("team_number") or "").strip()
    if not semester_label or not class_code or not team_number:
        return None

    semester_key = _semester_label_key(semester_label)
    if semester_key is None:
        return None
    year, season_name = semester_key
    return year, season_name, class_code, team_number


def _project_stable_key(project):
    return (
        str(project.semester.year),
        _normalized_text_key(project.semester.get_season_display()),
        project.class_code.strip(),
        project.team_number.strip(),
    )


def _rows_with_backfilled_project_ids(rows):
    """Add Project UUIDs to legacy share rows when their stable sheet key still resolves.

    Older saved-share JSON snapshots did not include ``id``. The frontend intentionally omits
    Individual Links for rows without an id, so enrich API output from the canonical
    Year-Semester + Class + Team# key when possible without mutating the stored snapshot.
    """
    missing_keys = {key for row in rows if not row.get("id") for key in [_share_row_stable_key(row)] if key is not None}
    if not missing_keys:
        return rows

    years = {int(key[0]) for key in missing_keys}
    class_codes = {key[2] for key in missing_keys}
    team_numbers = {key[3] for key in missing_keys}
    project_ids_by_key = {}
    projects = (
        Project.objects.select_related("semester")
        .filter(semester__year__in=years, class_code__in=class_codes, team_number__in=team_numbers)
        .order_by("-source", "pk")
    )
    for project in projects:
        key = _project_stable_key(project)
        if key in missing_keys and key not in project_ids_by_key:
            project_ids_by_key[key] = str(project.pk)

    if not project_ids_by_key:
        return rows

    enriched_rows = []
    for row in rows:
        next_row = dict(row)
        if not next_row.get("id"):
            key = _share_row_stable_key(next_row)
            project_id = project_ids_by_key.get(key)
            if project_id:
                next_row["id"] = project_id
        enriched_rows.append(next_row)
    return enriched_rows


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
    abstract = serializers.CharField(allow_blank=True)
    student_names = serializers.CharField(allow_blank=True)
    # Round-trip the frontend's presenting flag ('Yes'/'No'/'') so stored rows match freshly
    # searched rows — the client dedup fingerprint includes is_presenting, and dropping it here
    # made an owner's "add rows" re-add a project already in the share. Optional + default so
    # pre-existing shares (saved without the field) keep validating and serialize as "".
    is_presenting = serializers.CharField(max_length=10, allow_blank=True, required=False, default="")

    # noinspection PyMethodMayBeStatic
    def validate_id(self, value):
        try:
            return str(uuid.UUID(value))
        except (TypeError, ValueError, AttributeError):
            raise serializers.ValidationError("Enter a valid project UUID.")


class PastProjectShareSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=True, allow_blank=False, max_length=200)
    rows = PastProjectShareRowSerializer(many=True)
    note = serializers.CharField(
        required=False, allow_blank=True, default="", trim_whitespace=False, max_length=NOTE_MAX_LENGTH
    )
    details_text = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=DETAILS_TEXT_MAX_LENGTH
    )
    share_url = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = PastProjectShare
        fields = ["id", "name", "rows", "note", "details_text", "share_url", "can_edit", "created_at"]
        read_only_fields = ["id", "share_url", "can_edit", "created_at"]

    # name uses DRF CharField defaults (allow_blank=False + trim_whitespace=True), so
    # empty/whitespace-only names are rejected and the stored value is auto-trimmed —
    # no custom validate_name needed.

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["rows"] = _rows_with_backfilled_project_ids(data["rows"])
        return data

    # noinspection PyMethodMayBeStatic
    def validate_details_text(self, value):
        # Sanitize on write so stored/served details_text can never carry script or other
        # disallowed markup, regardless of how a client renders it.
        return sanitize_details_text(value)

    # noinspection PyMethodMayBeStatic
    def validate_note(self, value):
        # The note is rich text; sanitize on write with the same allowlist as details_text so a
        # stored note can never carry script or disallowed markup, however a client renders it.
        return sanitize_details_text(value)

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

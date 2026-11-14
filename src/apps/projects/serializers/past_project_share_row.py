"""One row of a share as a request carries it. The row is rebuilt from the catalog before it is stored."""

import uuid

from rest_framework import serializers

# Row text is rebuilt from the catalog, so these caps only bound a request: about ten times the longest archive
# abstract (~2,000 characters) and student list (~140).
ROW_ABSTRACT_MAX_LENGTH = 20_000
ROW_STUDENT_NAMES_MAX_LENGTH = 5_000


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
    # sent. The row is rebuilt from the catalog (services/shares/): "" for an archive project, and the
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

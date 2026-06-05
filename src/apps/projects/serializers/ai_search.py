from rest_framework import serializers


class PastProjectAISearchSerializer(serializers.Serializer):
    query = serializers.CharField(allow_blank=True, trim_whitespace=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=10, default=10)

    def __init__(self, *args, max_query_chars: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_query_chars = max_query_chars

    def validate_query(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Query must not be blank.")
        cap = self._max_query_chars
        if cap is not None and cap > 0 and len(value) > cap:
            raise serializers.ValidationError(f"Query must be at most {cap} characters.")
        return value

from rest_framework import serializers


class PublicAssistantHistoryItemSerializer(serializers.Serializer):
    """A single prior conversation turn."""

    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(allow_blank=False, trim_whitespace=True)


class PublicAssistantChatSerializer(serializers.Serializer):
    """Validate a public chat request.

    ``message`` is required, trimmed, non-empty, and length-capped. The cap is
    passed in by the view from ``SystemIntelligenceConfig`` so it stays
    admin-configurable. ``history`` is an optional list of {role, content}.
    """

    # trim_whitespace is disabled so the blank/length checks below own the
    # validation (and report a clear, single error message).
    message = serializers.CharField(allow_blank=True, trim_whitespace=False)
    history = PublicAssistantHistoryItemSerializer(many=True, required=False, default=list)
    # Client-supplied conversation id for audit grouping. Deliberately NOT
    # validated as a UUID here: a garbage id must group as a standalone turn,
    # never reject (400) the chat request.
    session_id = serializers.CharField(required=False, allow_blank=True, default="")

    def __init__(self, *args, max_message_chars: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_message_chars = max_message_chars

    def validate_message(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Message must not be blank.")
        cap = self._max_message_chars
        # A non-positive cap means "no limit" (matches the frontend, which
        # treats max_message_chars <= 0 as unlimited).
        if cap is not None and cap > 0 and len(value) > cap:
            raise serializers.ValidationError(f"Message must be at most {cap} characters.")
        return value

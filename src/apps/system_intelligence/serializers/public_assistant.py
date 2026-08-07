from rest_framework import serializers

MAX_PUBLIC_ASSISTANT_HISTORY_ITEMS = 100


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
    history = PublicAssistantHistoryItemSerializer(
        many=True,
        required=False,
        default=list,
        max_length=MAX_PUBLIC_ASSISTANT_HISTORY_ITEMS,
    )
    # Client-supplied conversation id for audit grouping. Deliberately NOT
    # validated as a UUID here: a garbage id must group as a standalone turn,
    # never reject (400) the chat request.
    session_id = serializers.CharField(required=False, allow_blank=True, default="")

    def __init__(
        self,
        *args,
        max_message_chars: int | None = None,
        max_history_chars: int | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._max_message_chars = max_message_chars
        self._max_history_chars = max_history_chars

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

    def validate_history(self, value: list[dict]) -> list[dict]:
        item_cap = self._max_message_chars
        if item_cap is not None and item_cap > 0:
            for item in value:
                if len(item["content"]) > item_cap:
                    raise serializers.ValidationError(f"Each history item must be at most {item_cap} characters.")
        total_cap = self._max_history_chars
        if total_cap is not None and total_cap > 0:
            total = sum(len(item["content"]) for item in value)
            first_retained = 0
            while first_retained < len(value) and total > total_cap:
                total -= len(value[first_retained]["content"])
                first_retained += 1
            if first_retained:
                value = value[first_retained:]
        return value

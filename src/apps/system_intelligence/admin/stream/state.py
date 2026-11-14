"""What one chat stream remembers while it runs, and the final event it ends with."""

from dataclasses import dataclass, field

from .helpers import _sse


@dataclass
class _StreamState:
    """What one assistant turn has produced so far."""

    full_text: str = ""
    tool_calls: list = field(default_factory=list)
    action_ids: list = field(default_factory=list)
    action_requests: list = field(default_factory=list)
    total_usage: dict = field(default_factory=lambda: {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0})
    context_usage: dict = field(default_factory=dict)
    prepared_context: object = None
    stopped: bool = False


def _done_event(convo, assistant, model_id, tool_calls, action_requests, total_usage, context_usage):
    return _sse(
        "done",
        {
            "id": str(assistant.id),
            "model_id": model_id,
            "title": convo.title,
            "tool_calls": tool_calls,
            "action_requests": action_requests,
            "token_usage": total_usage,
            "context_usage": context_usage,
        },
    )

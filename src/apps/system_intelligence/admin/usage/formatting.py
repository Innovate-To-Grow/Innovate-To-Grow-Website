"""How the usage log shows a conversation: token counts, colors, JSON, and the transcript turns."""

import json

from django.template.defaultfilters import linebreaksbr
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog

_SOURCE_COLORS = {
    AssistantConversationLog.SOURCE_PUBLIC_CHAT: "info",
    AssistantConversationLog.SOURCE_AI_SEARCH: "primary",
}
_STATUS_COLORS = {
    AssistantMessageLog.STATUS_OK: "success",
    AssistantMessageLog.STATUS_ERROR: "danger",
    AssistantMessageLog.STATUS_BUDGET: "warning",
    AssistantMessageLog.STATUS_UNAVAILABLE: "info",
}


def _token_value(usage, key):
    if not isinstance(usage, dict):
        return 0
    try:
        return int(usage.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _linebreaks(value):
    return linebreaksbr(str(value or "—"))


def _pretty_json(value):
    if not value:
        return ""
    return json.dumps(value, indent=2, sort_keys=True)


def _turn_meta(index: int, message) -> list[str]:
    usage = message.token_usage or {}
    meta = [
        f"Turn {index}",
        message.get_status_display(),
        f"Total: {_token_value(usage, 'totalTokens'):,}",
        f"Input: {_token_value(usage, 'inputTokens'):,}",
        f"Output: {_token_value(usage, 'outputTokens'):,}",
        f"Latency: {message.latency_ms:,} ms",
    ]
    if message.model_id:
        meta.append(message.model_id)
    if message.created_at:
        meta.append(timezone.localtime(message.created_at).strftime("%Y-%m-%d %H:%M:%S %Z"))
    return meta


def _transcript_turn(index: int, message):
    meta_html = format_html_join(
        "", '<span class="si-transcript-chip">{}</span>', ((item,) for item in _turn_meta(index, message))
    )
    reply_html = (
        format_html(
            """
            <div class="si-transcript-block si-transcript-block--assistant">
              <div class="si-transcript-label">Assistant</div>
              <div class="si-transcript-text">{}</div>
            </div>
            """,
            _linebreaks(message.reply),
        )
        if message.reply
        else ""
    )
    results_html = (
        format_html(
            """
            <div class="si-transcript-block">
              <div class="si-transcript-label">Results</div>
              <pre class="si-transcript-json">{}</pre>
            </div>
            """,
            _pretty_json(message.results),
        )
        if message.results
        else ""
    )
    return format_html(
        """
        <article class="si-transcript-turn">
          <div class="si-transcript-meta">{}</div>
          <div class="si-transcript-block si-transcript-block--user">
            <div class="si-transcript-label">User</div>
            <div class="si-transcript-text">{}</div>
          </div>
          {}{}
        </article>
        """,
        meta_html,
        _linebreaks(message.prompt),
        reply_html,
        results_html,
    )

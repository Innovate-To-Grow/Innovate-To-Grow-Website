"""Audit recorder for public-assistant and AI-search turns.

The single public entrypoint, :func:`log_assistant_turn`, persists one turn
(and its conversation grouping) for admin audit. It is intentionally
best-effort: its entire body is guarded so that a logging failure can NEVER
break the user-facing request.
"""

import logging
import uuid

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    SystemIntelligenceConfig,
)

logger = logging.getLogger(__name__)


def _coerce_session_uuid(session_id) -> uuid.UUID | None:
    """Return a UUID for a client-supplied session id, or None if unusable."""
    if not session_id:
        return None
    if isinstance(session_id, uuid.UUID):
        return session_id
    try:
        return uuid.UUID(str(session_id))
    except (ValueError, AttributeError, TypeError):
        return None


def log_assistant_turn(
    *,
    source,
    session_id,
    ip_hash,
    user=None,
    prompt,
    reply="",
    results=None,
    status,
    model_id="",
    token_usage=None,
    latency_ms=0,
    config=None,
) -> None:
    """Persist one audited assistant turn. Never raises.

    A garbage/blank ``session_id`` is treated as None (standalone
    conversation). Callers that already loaded the active config may pass it in
    via ``config`` to avoid a second DB read.
    """
    try:
        if config is None:
            config = SystemIntelligenceConfig.load()
        if not config.public_assistant_log_enabled:
            return

        token_usage = token_usage or {}
        results = results if results is not None else []
        now = timezone.now()
        session_uuid = _coerce_session_uuid(session_id)
        spent = token_usage.get("totalTokens") or 0

        with transaction.atomic():
            # New conversations are created with this turn's counters baked in
            # (single INSERT); only reused conversations need the follow-up
            # UPDATE below.
            created = True
            if session_uuid is not None:
                conversation, created = AssistantConversationLog.objects.get_or_create(
                    source=source,
                    session_id=session_uuid,
                    defaults={
                        "ip_hash": ip_hash,
                        "user": user,
                        "message_count": 1,
                        "total_tokens": spent,
                        "last_activity_at": now,
                    },
                )
            else:
                conversation = AssistantConversationLog.objects.create(
                    source=source,
                    session_id=None,
                    ip_hash=ip_hash,
                    user=user,
                    message_count=1,
                    total_tokens=spent,
                    last_activity_at=now,
                )

            AssistantMessageLog.objects.create(
                conversation=conversation,
                prompt=prompt,
                reply=reply or "",
                results=results,
                status=status,
                model_id=model_id or "",
                token_usage=token_usage,
                latency_ms=latency_ms,
            )

            if not created:
                # F() expressions so concurrent turns on the same session
                # increment atomically in the database (no lost updates from
                # read-modify-write races).
                update_fields = ["message_count", "total_tokens", "last_activity_at", "updated_at"]
                conversation.message_count = F("message_count") + 1
                conversation.total_tokens = F("total_tokens") + spent
                conversation.last_activity_at = now
                if not conversation.ip_hash and ip_hash:
                    conversation.ip_hash = ip_hash
                    update_fields.append("ip_hash")
                if conversation.user is None and user is not None:
                    conversation.user = user
                    update_fields.append("user")
                conversation.save(update_fields=update_fields)
    except Exception:
        try:
            logger.exception("Failed to record assistant turn for audit (source=%s)", source)
        except Exception:  # nosec B110 -- the never-raise contract outranks reporting a broken log handler
            # Even logging can fail (broken handler); auditing must stay silent.
            pass
        return

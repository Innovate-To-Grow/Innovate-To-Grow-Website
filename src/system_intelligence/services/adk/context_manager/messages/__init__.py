from system_intelligence.models import ChatConversation, ChatMessage, SystemIntelligenceActionRequest


def serialize_message(message: ChatMessage) -> dict[str, str]:
    return {"role": message.role, "content": message.content or ""}


def format_messages_for_summary(messages: list[ChatMessage]) -> str:
    chunks = []
    for message in messages:
        created_at = message.created_at.isoformat() if message.created_at else ""
        chunks.append(f"[{message.role} {message.pk} {created_at}]\n{message.content or ''}".strip())
        for action in list(getattr(message, "action_requests", []).all()):
            chunks.append(
                "Action request "
                f"{action.id}: {action.title} status={action.status} target={action.target_app_label}."
                f"{action.target_model}:{action.target_pk} summary={action.summary}"
            )
    return "\n\n".join(chunks)


def pending_action_context_message(conversation: ChatConversation) -> dict[str, str] | None:
    pending_actions = list(
        conversation.action_requests.filter(status=SystemIntelligenceActionRequest.STATUS_PENDING).order_by(
            "created_at"
        )[:20]
    )
    if not pending_actions:
        return None
    lines = [
        "Pending System Intelligence approval requests. These are not applied until an admin approves them:",
    ]
    for action in pending_actions:
        target = ".".join(part for part in [action.target_app_label, action.target_model] if part)
        if action.target_pk:
            target = f"{target} #{action.target_pk}" if target else f"#{action.target_pk}"
        lines.append(
            f"- {action.id}: {action.title} status={action.status} type={action.action_type} "
            f"target={target or 'unknown'} summary={action.summary or '(none)'}"
        )
    return {"role": "assistant", "content": "\n".join(lines)}


def summary_context_message(summary_text: str) -> dict[str, str]:
    return {
        "role": "assistant",
        "content": "Rolling summary of earlier System Intelligence conversation context:\n" + summary_text,
    }

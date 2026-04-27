import contextvars

from django.contrib.auth import get_user_model

from core.models.base.system_intelligence import ChatConversation

from .exceptions import ActionRequestError

ACTION_CONVERSATION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "system_intelligence_action_conversation_id",
    default=None,
)
ACTION_USER_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "system_intelligence_action_user_id",
    default=None,
)


def set_action_context(conversation_id: str | None, user_id: str | None) -> tuple[contextvars.Token, contextvars.Token]:
    """Store chat context for ADK tools that run without direct request args."""
    return (
        ACTION_CONVERSATION_ID.set(str(conversation_id) if conversation_id else None),
        ACTION_USER_ID.set(str(user_id) if user_id else None),
    )


def reset_action_context(tokens: tuple[contextvars.Token, contextvars.Token]) -> None:
    """Reset contextvars set by set_action_context."""
    ACTION_CONVERSATION_ID.reset(tokens[0])
    ACTION_USER_ID.reset(tokens[1])


def current_conversation() -> ChatConversation:
    conversation_id = ACTION_CONVERSATION_ID.get()
    if not conversation_id:
        raise ActionRequestError("No active chat conversation is available for this action request.")
    try:
        return ChatConversation.objects.get(id=conversation_id)
    except ChatConversation.DoesNotExist as exc:
        raise ActionRequestError("Active chat conversation was not found.") from exc


def current_user_id() -> str | None:
    return ACTION_USER_ID.get()


def current_user():
    """Resolve the active staff user for permission checks; returns None if not set."""
    user_id = ACTION_USER_ID.get()
    if not user_id:
        return None
    User = get_user_model()
    try:
        return User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError, TypeError):
        return None

from collections.abc import Iterable

from google.adk.events import Event
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .constants import AGENT_NAME
from .errors import SystemIntelligenceADKError


def split_history_and_current_message(messages: Iterable[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    items = list(messages)
    if not items:
        raise SystemIntelligenceADKError("Message history is empty.")
    current = items[-1]
    if current.get("role") != "user":
        raise SystemIntelligenceADKError("The latest message must be a user message.")
    user_message = (current.get("content") or "").strip()
    if not user_message:
        raise SystemIntelligenceADKError("Message cannot be empty.")
    return items[:-1], user_message


async def seed_session_history(
    session_service: InMemorySessionService, session, messages: Iterable[dict[str, str]]
) -> None:
    for message in messages:
        content = (message.get("content") or "").strip()
        if not content:
            continue
        role = message.get("role")
        if role == "user":
            event_role = "user"
            author = "user"
        elif role == "assistant":
            event_role = "model"
            author = AGENT_NAME
        else:
            continue
        await session_service.append_event(
            session=session,
            event=Event(
                author=author, content=types.Content(role=event_role, parts=[types.Part.from_text(text=content)])
            ),
        )

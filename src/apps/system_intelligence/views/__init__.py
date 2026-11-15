"""Public, visitor-facing assistant API.

Endpoints (mounted at ``/assistant/``):
  - POST /assistant/chat/   -- tool-free, read-only chat
  - GET  /assistant/config/ -- public-safe display config

The chat path is graceful: when the assistant is disabled or the backing
AWS/model is not configured it returns HTTP 200 with ``available: false`` so
the frontend widget can render an unavailable state instead of erroring.

Limits are keyed on the ACTOR (see ``services/public_assistant/chat/actors.py``),
never on the client IP: ``GET /assistant/config/`` hands the browser a signed
``visitor_token`` and the widget returns it in the chat request body. A chat
request without a usable one is still answered, in the shared ``legacy``
bucket, and its response carries a ``visitor_token`` for the client to store.
"""

from .endpoints import PublicAssistantChatView, PublicAssistantConfigView
from .throttle import PublicAssistantActorThrottle

__all__ = ["PublicAssistantActorThrottle", "PublicAssistantChatView", "PublicAssistantConfigView"]

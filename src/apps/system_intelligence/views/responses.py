"""The public assistant's plain responses: a JSON body, and the answer while it is unavailable."""

from rest_framework import status
from rest_framework.response import Response

from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.public_assistant import (
    VISITOR_FIELD,
    AssistantActor,
)


def _body(payload: dict, actor: AssistantActor | None = None) -> dict:
    """Attach the visitor value the client should store, when there is one."""
    if actor is not None and actor.replacement:
        payload[VISITOR_FIELD] = actor.replacement
    return payload


def _unavailable_response(config: SystemIntelligenceConfig, actor: AssistantActor | None = None) -> Response:
    return Response(
        _body({"available": False, "message": config.public_assistant_unavailable_message}, actor),
        status=status.HTTP_200_OK,
    )

"""Public, visitor-facing assistant API.

Endpoints (mounted at ``/assistant/``):
  - POST /assistant/chat/   -- tool-free, read-only chat
  - GET  /assistant/config/ -- public-safe display config

The chat path is graceful: when the assistant is disabled or the backing
AWS/model is not configured it returns HTTP 200 with ``available: false`` so
the frontend widget can render an unavailable state instead of erroring.
"""

import logging
import time

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.models import AWSCredentialConfig
from apps.core.services.bedrock import normalize_bedrock_model_id
from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog, SystemIntelligenceConfig
from apps.system_intelligence.serializers import PublicAssistantChatSerializer
from apps.system_intelligence.services.public_assistant import (
    answer_public_question,
    check_budget,
    client_ip,
    hash_ip,
    record_usage,
)
from apps.system_intelligence.services.usage_log import log_assistant_turn

logger = logging.getLogger(__name__)

_BUDGET_MESSAGE = "You've reached the assistant usage limit for now. Please try again later."
_ERROR_MESSAGE = "The assistant ran into a problem answering that. Please try again in a moment."


class PublicAssistantThrottle(AnonRateThrottle):
    scope = "public_assistant"


def _unavailable_response(config: SystemIntelligenceConfig) -> Response:
    return Response(
        {"available": False, "message": config.public_assistant_unavailable_message},
        status=status.HTTP_200_OK,
    )


class PublicAssistantConfigView(APIView):
    """GET /assistant/config/ -- public-safe display config only (never secrets)."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        config = SystemIntelligenceConfig.load()
        starter_questions = config.public_assistant_starter_questions
        if not isinstance(starter_questions, list):
            starter_questions = []
        return Response(
            {
                "enabled": config.public_assistant_enabled,
                "welcome_message": config.public_assistant_welcome_message,
                "starter_questions": starter_questions,
                "unavailable_message": config.public_assistant_unavailable_message,
                "max_message_chars": config.public_assistant_max_message_chars,
            },
            status=status.HTTP_200_OK,
        )


class PublicAssistantChatView(APIView):
    """POST /assistant/chat/ -- tool-free, read-only public chat."""

    permission_classes = [AllowAny]
    throttle_classes = [PublicAssistantThrottle]

    def post(self, request, *args, **kwargs):
        config = SystemIntelligenceConfig.load()

        # 1. Disabled -> graceful unavailable.
        if not config.public_assistant_enabled:
            return _unavailable_response(config)

        # 2. Validate payload (400 on failure).
        serializer = PublicAssistantChatSerializer(
            data=request.data,
            max_message_chars=config.public_assistant_max_message_chars,
        )
        serializer.is_valid(raise_exception=True)
        message = serializer.validated_data["message"]
        session_id = serializer.validated_data.get("session_id", "")
        history = serializer.validated_data.get("history", [])
        history_limit = config.public_assistant_max_history_messages
        # history[-0:] is the whole list, so handle a zero limit explicitly.
        history = history[-history_limit:] if history_limit else []

        # ip_hash is computed up front so every terminal branch can audit it.
        ip_hash = hash_ip(client_ip(request) or "")
        model_id = normalize_bedrock_model_id(config.public_model_id) or ""

        # 3. AWS / model not configured -> graceful unavailable.
        aws_config = AWSCredentialConfig.load()
        if not aws_config.is_configured or not model_id:
            log_assistant_turn(
                source=AssistantConversationLog.SOURCE_PUBLIC_CHAT,
                session_id=session_id,
                ip_hash=ip_hash,
                prompt=message,
                status=AssistantMessageLog.STATUS_UNAVAILABLE,
                model_id=model_id,
                config=config,
            )
            return _unavailable_response(config)

        # 4. Per-IP token budget (checked BEFORE the model call).
        if not check_budget(ip_hash, config.public_assistant_ip_token_limit):
            log_assistant_turn(
                source=AssistantConversationLog.SOURCE_PUBLIC_CHAT,
                session_id=session_id,
                ip_hash=ip_hash,
                prompt=message,
                status=AssistantMessageLog.STATUS_BUDGET,
                model_id=model_id,
                config=config,
            )
            return Response(
                {"detail": _BUDGET_MESSAGE, "code": "budget_exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # 5. Invoke the tool-free model.
        started = time.monotonic()
        try:
            result = answer_public_question(message=message, history=history, config=config)
        except Exception:
            logger.exception("Public assistant invocation failed")
            log_assistant_turn(
                source=AssistantConversationLog.SOURCE_PUBLIC_CHAT,
                session_id=session_id,
                ip_hash=ip_hash,
                prompt=message,
                status=AssistantMessageLog.STATUS_ERROR,
                model_id=model_id,
                latency_ms=int((time.monotonic() - started) * 1000),
                config=config,
            )
            return Response(
                {"detail": _ERROR_MESSAGE, "code": "assistant_error"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        latency_ms = int((time.monotonic() - started) * 1000)

        # 6. Record usage and return.
        usage = result.get("usage") or {}
        spent = usage.get("totalTokens") or 0
        record_usage(ip_hash, spent, config.public_assistant_ip_token_window_seconds)
        reply = result.get("text", "")
        log_assistant_turn(
            source=AssistantConversationLog.SOURCE_PUBLIC_CHAT,
            session_id=session_id,
            ip_hash=ip_hash,
            prompt=message,
            reply=reply,
            status=AssistantMessageLog.STATUS_OK,
            model_id=model_id,
            token_usage=usage,
            latency_ms=latency_ms,
            config=config,
        )
        return Response(
            {"available": True, "reply": reply, "usage": usage},
            status=status.HTTP_200_OK,
        )

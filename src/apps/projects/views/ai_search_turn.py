"""What one AI-search request records in the assistant audit log, and the responses for an error and for AI search
not being configured."""

import logging
import time
from dataclasses import dataclass

from rest_framework import status
from rest_framework.response import Response

from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog, SystemIntelligenceConfig
from apps.system_intelligence.services.usage_log import log_assistant_turn

# These helpers used to live in ``ai_search``; keep that logger name.
logger = logging.getLogger("apps.projects.views.ai_search")

_ERROR_MESSAGE = "AI search ran into a problem. Please try again in a moment."
# Shown to members; the operator-facing cause goes to the log.
_UNAVAILABLE_MESSAGE = "AI search isn't available right now. You can still search with a search table."


def _unavailable_response(config: SystemIntelligenceConfig, query: str = "") -> Response:
    logger.warning("Past project AI search is not configured: set the AWS Bedrock credentials and the public model.")
    return Response(
        {
            "available": False,
            "message": _UNAVAILABLE_MESSAGE,
            "query": query,
            "results": [],
            "usage": {},
        },
        status=status.HTTP_200_OK,
    )


@dataclass
class _SearchTurn:
    """One AI-search request: what every audit-log entry for it records, and the scope it searches."""

    request: object
    config: SystemIntelligenceConfig
    query: str
    ip_hash: str
    model_id: str
    # "past" or "all" (apps.projects.services.ai_search.candidates). The audit log does not record it.
    scope: str

    def log(self, status_value, **extra) -> None:
        log_assistant_turn(
            source=AssistantConversationLog.SOURCE_AI_SEARCH,
            session_id=None,
            ip_hash=self.ip_hash,
            user=self.request.user,
            prompt=self.query,
            status=status_value,
            model_id=self.model_id,
            config=self.config,
            **extra,
        )

    def error_response(self, started_at: float) -> Response:
        self.log(AssistantMessageLog.STATUS_ERROR, latency_ms=int((time.monotonic() - started_at) * 1000))
        return Response({"detail": _ERROR_MESSAGE, "code": "ai_search_error"}, status=status.HTTP_502_BAD_GATEWAY)

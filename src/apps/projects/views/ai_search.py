import logging
import time

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import AWSCredentialConfig
from apps.core.services.bedrock import normalize_bedrock_model_id
from apps.projects.serializers import PastProjectAISearchSerializer, ProjectTableSerializer
from apps.projects.services.ai_search import past_project_ai_queryset, run_past_project_ai_search
from apps.projects.throttles import PastProjectAISearchRateThrottle
from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog, SystemIntelligenceConfig
from apps.system_intelligence.services.public_assistant import check_budget, client_ip, hash_ip, record_usage
from apps.system_intelligence.services.usage_log import log_assistant_turn

logger = logging.getLogger(__name__)

_BUDGET_MESSAGE = "You've reached the AI search usage limit for now. Please try again later."
_ERROR_MESSAGE = "AI search ran into a problem. Please try again in a moment."
_UNAVAILABLE_MESSAGE = "AI search is not configured yet. Check the AWS Bedrock credentials and model settings."


def _unavailable_response(config: SystemIntelligenceConfig, query: str = "") -> Response:
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


class PastProjectAISearchAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PastProjectAISearchRateThrottle]

    def post(self, request, *args, **kwargs):
        config = SystemIntelligenceConfig.load()
        serializer = PastProjectAISearchSerializer(
            data=request.data,
            max_query_chars=config.public_assistant_max_message_chars,
        )
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data["query"]
        limit = serializer.validated_data["limit"]

        ip_hash = hash_ip(client_ip(request) or "")
        model_id = normalize_bedrock_model_id(config.public_model_id) or ""

        aws_config = AWSCredentialConfig.load()
        if not aws_config.is_configured or not model_id:
            log_assistant_turn(
                source=AssistantConversationLog.SOURCE_AI_SEARCH,
                session_id=None,
                ip_hash=ip_hash,
                user=request.user,
                prompt=query,
                status=AssistantMessageLog.STATUS_UNAVAILABLE,
                model_id=model_id,
                config=config,
            )
            return _unavailable_response(config, query)

        if not check_budget(ip_hash, config.public_assistant_ip_token_limit):
            log_assistant_turn(
                source=AssistantConversationLog.SOURCE_AI_SEARCH,
                session_id=None,
                ip_hash=ip_hash,
                user=request.user,
                prompt=query,
                status=AssistantMessageLog.STATUS_BUDGET,
                model_id=model_id,
                config=config,
            )
            return Response(
                {"detail": _BUDGET_MESSAGE, "code": "budget_exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        started = time.monotonic()
        try:
            outcome = run_past_project_ai_search(query=query, limit=limit, config=config)
        except Exception:
            logger.exception("Past project AI search invocation failed")
            log_assistant_turn(
                source=AssistantConversationLog.SOURCE_AI_SEARCH,
                session_id=None,
                ip_hash=ip_hash,
                user=request.user,
                prompt=query,
                status=AssistantMessageLog.STATUS_ERROR,
                model_id=model_id,
                latency_ms=int((time.monotonic() - started) * 1000),
                config=config,
            )
            return Response(
                {"detail": _ERROR_MESSAGE, "code": "ai_search_error"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        latency_ms = int((time.monotonic() - started) * 1000)

        usage = outcome.get("usage") or {}
        spent = usage.get("totalTokens") or 0
        record_usage(ip_hash, spent, config.public_assistant_ip_token_window_seconds)

        project_ids = outcome.get("project_ids") or []
        projects_by_id = {str(project.id): project for project in past_project_ai_queryset().filter(id__in=project_ids)}
        ordered_projects = [projects_by_id[project_id] for project_id in project_ids if project_id in projects_by_id]

        log_assistant_turn(
            source=AssistantConversationLog.SOURCE_AI_SEARCH,
            session_id=None,
            ip_hash=ip_hash,
            user=request.user,
            prompt=query,
            results=[{"id": str(p.id), "project_title": p.project_title} for p in ordered_projects],
            status=AssistantMessageLog.STATUS_OK,
            model_id=model_id,
            token_usage=usage,
            latency_ms=latency_ms,
            config=config,
        )

        return Response(
            {
                "available": True,
                "query": query,
                "results": ProjectTableSerializer(ordered_projects, many=True).data,
                "usage": usage,
            },
            status=status.HTTP_200_OK,
        )

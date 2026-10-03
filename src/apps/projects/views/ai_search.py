import logging
import time

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import AWSCredentialConfig
from apps.core.services.bedrock import normalize_bedrock_model_id
from apps.projects.serializers import PastProjectAISearchSerializer, ProjectTableSerializer
from apps.projects.services.ai_search import (
    past_project_ai_queryset,
    prepare_past_project_ai_search,
    run_past_project_ai_search,
)
from apps.projects.throttles import PastProjectAISearchRateThrottle
from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog, SystemIntelligenceConfig
from apps.system_intelligence.services.public_assistant import (
    FEATURE_AI_SEARCH,
    BudgetBackendUnavailable,
    client_ip,
    hash_ip,
    member_actor,
    reconcile_budget,
    release_budget,
    reported_total_tokens,
    reserve_budget,
    sanitized_usage,
)
from apps.system_intelligence.services.usage_log import log_assistant_turn

logger = logging.getLogger(__name__)

# Deliberately impersonal: the limit that was hit may be the member's own
# budget or AI search's global one (which the public assistant cannot use up:
# it has a separate global budget).
_BUDGET_MESSAGE = "AI search has reached its usage limit for now. Please try again later."
_BUDGET_UNAVAILABLE_MESSAGE = "AI search is temporarily unavailable. Please try again in a moment."
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

        # Token budgets are keyed on the MEMBER, never on the client IP (the
        # whole campus shares one). ip_hash is recorded in the audit log only.
        actor = member_actor(request.user.pk)
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

        def error_response(started_at: float) -> Response:
            log_assistant_turn(
                source=AssistantConversationLog.SOURCE_AI_SEARCH,
                session_id=None,
                ip_hash=ip_hash,
                user=request.user,
                prompt=query,
                status=AssistantMessageLog.STATUS_ERROR,
                model_id=model_id,
                latency_ms=int((time.monotonic() - started_at) * 1000),
                config=config,
            )
            return Response(
                {"detail": _ERROR_MESSAGE, "code": "ai_search_error"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Build the prompt first so its size is known, then reserve estimated
        # input + the output cap against the member's budget AND AI search's
        # own global budget before spending anything. No candidates -> no model
        # call and nothing to reserve.
        started = time.monotonic()
        try:
            prepared = prepare_past_project_ai_search(query=query, limit=limit, config=config)
        except Exception:
            logger.exception("Past project AI search preparation failed")
            return error_response(started)
        reservation = None
        if prepared is not None:
            try:
                reservation = reserve_budget(
                    actor.key,
                    estimated_input_tokens=prepared.estimated_input_tokens,
                    maximum_output_tokens=prepared.max_tokens,
                    limit=config.public_assistant_ip_token_limit,
                    window_seconds=config.public_assistant_ip_token_window_seconds,
                    global_limit=config.public_assistant_global_token_limit,
                    feature=FEATURE_AI_SEARCH,
                )
            except BudgetBackendUnavailable:
                logger.exception("Past project AI search budget is unavailable")
                return Response(
                    {"detail": _BUDGET_UNAVAILABLE_MESSAGE, "code": "budget_unavailable"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        if prepared is not None and reservation is None:
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
        outcome = {"project_ids": [], "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}}
        if reservation is not None:
            try:
                outcome = run_past_project_ai_search(query=query, limit=limit, config=config, prepared=prepared)
            except Exception:
                logger.exception("Past project AI search invocation failed")
                # Nothing was (successfully) spent: give the whole reservation back.
                try:
                    release_budget(reservation)
                except BudgetBackendUnavailable:
                    logger.exception("Could not release failed AI-search reservation")
                return error_response(started)
        latency_ms = int((time.monotonic() - started) * 1000)

        raw_usage = outcome.get("usage")
        if reservation is not None:
            # Replace the reservation with what the provider actually charged.
            try:
                reconcile_budget(reservation, reported_total_tokens(raw_usage))
            except BudgetBackendUnavailable:
                logger.exception("Could not reconcile AI-search reservation")
        # Only plausible integers are stored and returned: the raw block is provider-controlled.
        usage = sanitized_usage(raw_usage)

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

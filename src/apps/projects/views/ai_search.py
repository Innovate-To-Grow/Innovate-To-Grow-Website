import logging
import time
from dataclasses import dataclass

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import AWSCredentialConfig
from apps.projects.serializers import PastProjectAISearchSerializer, ProjectTableSerializer
from apps.projects.services.ai_search import (
    past_project_ai_queryset,
    prepare_past_project_ai_search,
    run_past_project_ai_search,
)
from apps.projects.throttles import PastProjectAISearchRateThrottle
from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog, SystemIntelligenceConfig
from apps.system_intelligence.services.bedrock import normalize_bedrock_model_id
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


@dataclass
class _SearchTurn:
    """One AI-search request: what every audit-log entry for it records."""

    request: object
    config: SystemIntelligenceConfig
    query: str
    ip_hash: str
    model_id: str

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


def _reserve_search_budget(actor, prepared, config):
    """Reserve estimated input + the output cap against the member's and AI search's global budget.

    Returns the reservation, or a refusal ``Response`` (budget exhausted or its backend unreachable).
    """
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
    return reservation


def _run_and_settle(turn: _SearchTurn, *, limit, prepared, reservation):
    """Invoke the model and settle the reservation; returns (outcome, latency_ms) or an error ``Response``."""
    started = time.monotonic()
    outcome = {"project_ids": [], "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}}
    if reservation is not None:
        try:
            outcome = run_past_project_ai_search(query=turn.query, limit=limit, config=turn.config, prepared=prepared)
        except Exception:
            logger.exception("Past project AI search invocation failed")
            # Nothing was (successfully) spent: give the whole reservation back.
            try:
                release_budget(reservation)
            except BudgetBackendUnavailable:
                logger.exception("Could not release failed AI-search reservation")
            return turn.error_response(started)
    latency_ms = int((time.monotonic() - started) * 1000)
    if reservation is not None:
        # Replace the reservation with what the provider actually charged.
        try:
            reconcile_budget(reservation, reported_total_tokens(outcome.get("usage")))
        except BudgetBackendUnavailable:
            logger.exception("Could not reconcile AI-search reservation")
    return outcome, latency_ms


def _results_response(turn: _SearchTurn, outcome, latency_ms) -> Response:
    # Only plausible integers are stored and returned: the raw block is provider-controlled.
    usage = sanitized_usage(outcome.get("usage"))
    project_ids = outcome.get("project_ids") or []
    projects_by_id = {str(project.id): project for project in past_project_ai_queryset().filter(id__in=project_ids)}
    ordered_projects = [projects_by_id[project_id] for project_id in project_ids if project_id in projects_by_id]
    turn.log(
        AssistantMessageLog.STATUS_OK,
        results=[{"id": str(p.id), "project_title": p.project_title} for p in ordered_projects],
        token_usage=usage,
        latency_ms=latency_ms,
    )
    return Response(
        {
            "available": True,
            "query": turn.query,
            "results": ProjectTableSerializer(ordered_projects, many=True).data,
            "usage": usage,
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
        turn = _SearchTurn(
            request=request,
            config=config,
            query=query,
            ip_hash=hash_ip(client_ip(request) or ""),
            model_id=normalize_bedrock_model_id(config.public_model_id) or "",
        )
        if not AWSCredentialConfig.load().is_configured or not turn.model_id:
            turn.log(AssistantMessageLog.STATUS_UNAVAILABLE)
            return _unavailable_response(config, query)

        # Build the prompt first so its size is known, then reserve before spending
        # anything. No candidates -> no model call and nothing to reserve.
        started = time.monotonic()
        try:
            prepared = prepare_past_project_ai_search(query=query, limit=limit, config=config)
        except Exception:
            logger.exception("Past project AI search preparation failed")
            return turn.error_response(started)
        reservation = None
        if prepared is not None:
            reservation = _reserve_search_budget(actor, prepared, config)
            if isinstance(reservation, Response):
                return reservation
            if reservation is None:
                turn.log(AssistantMessageLog.STATUS_BUDGET)
                return Response(
                    {"detail": _BUDGET_MESSAGE, "code": "budget_exceeded"},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        settled = _run_and_settle(turn, limit=limit, prepared=prepared, reservation=reservation)
        if isinstance(settled, Response):
            return settled
        outcome, latency_ms = settled
        return _results_response(turn, outcome, latency_ms)

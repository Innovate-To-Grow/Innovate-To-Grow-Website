"""One chat turn of the public assistant: its input and context, the budget reservation, and the answer."""

import logging
import time
from dataclasses import dataclass

from rest_framework import status
from rest_framework.response import Response

from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog, SystemIntelligenceConfig
from apps.system_intelligence.services.public_assistant import (
    FEATURE_ASSISTANT,
    BudgetBackendUnavailable,
    actor_token_limit,
    answer_public_question,
    build_public_context,
    estimate_public_input_tokens,
    reconcile_budget,
    release_budget,
    reported_total_tokens,
    reserve_budget,
    sanitized_usage,
)
from apps.system_intelligence.services.usage_log import log_assistant_turn

from .responses import _body

logger = logging.getLogger(__name__)

# Deliberately impersonal: the limit that was hit may be the assistant's global
# budget rather than the asker's own, so it must not blame the person asking.
_BUDGET_MESSAGE = "The assistant has reached its usage limit for now. Please try again later."
_ERROR_MESSAGE = "The assistant ran into a problem answering that. Please try again in a moment."
_BUDGET_UNAVAILABLE_MESSAGE = "The assistant is temporarily unavailable. Please try again in a moment."


@dataclass
class _ChatTurn:
    """One chat request: what every audit-log entry and response body for it needs."""

    config: SystemIntelligenceConfig
    actor: object
    message: str
    session_id: str
    history: list
    ip_hash: str
    model_id: str

    def log(self, status_value, **extra) -> None:
        log_assistant_turn(
            source=AssistantConversationLog.SOURCE_PUBLIC_CHAT,
            session_id=self.session_id,
            ip_hash=self.ip_hash,
            prompt=self.message,
            status=status_value,
            model_id=self.model_id,
            config=self.config,
            **extra,
        )

    def respond(self, payload: dict, status_code: int) -> Response:
        return Response(_body(payload, self.actor), status=status_code)


def _prepare_chat_input(turn: _ChatTurn):
    """The public context and the estimated input size; or a refusal ``Response``."""
    config = turn.config
    try:
        context = build_public_context(char_cap=config.public_assistant_max_context_chars)
    except Exception:
        logger.exception("Public assistant context cache is unavailable")
        return turn.respond(
            {"detail": _BUDGET_UNAVAILABLE_MESSAGE, "code": "budget_unavailable"},
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    estimated_input = estimate_public_input_tokens(
        message=turn.message,
        history=turn.history,
        config=config,
        context=context,
    )
    input_limit = config.public_assistant_max_estimated_input_tokens
    if input_limit > 0 and estimated_input > input_limit:
        return turn.respond(
            {"detail": "The request is too large for the public assistant.", "code": "input_too_large"},
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    return context, estimated_input


def _reserve_chat_budget(turn: _ChatTurn, estimated_input: int):
    """The budget reservation, or a refusal ``Response`` (budget exhausted or its backend unreachable)."""
    config = turn.config
    try:
        reservation = reserve_budget(
            turn.actor.key,
            estimated_input_tokens=estimated_input,
            maximum_output_tokens=config.public_assistant_max_response_tokens,
            limit=actor_token_limit(turn.actor, config.public_assistant_ip_token_limit),
            window_seconds=config.public_assistant_ip_token_window_seconds,
            global_limit=config.public_assistant_global_token_limit,
            feature=FEATURE_ASSISTANT,
        )
    except BudgetBackendUnavailable:
        logger.exception("Public assistant shared budget is unavailable")
        return turn.respond(
            {"detail": _BUDGET_UNAVAILABLE_MESSAGE, "code": "budget_unavailable"},
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if reservation is None:
        turn.log(AssistantMessageLog.STATUS_BUDGET)
        return turn.respond({"detail": _BUDGET_MESSAGE, "code": "budget_exceeded"}, status.HTTP_429_TOO_MANY_REQUESTS)
    return reservation


def _answer_and_settle(turn: _ChatTurn, context, reservation) -> Response:
    started = time.monotonic()
    try:
        result = answer_public_question(
            message=turn.message,
            history=turn.history,
            config=turn.config,
            context=context,
        )
    except Exception:
        logger.exception("Public assistant invocation failed")
        try:
            release_budget(reservation)
        except BudgetBackendUnavailable:
            logger.exception("Could not release failed public-assistant reservation")
        turn.log(AssistantMessageLog.STATUS_ERROR, latency_ms=int((time.monotonic() - started) * 1000))
        return turn.respond({"detail": _ERROR_MESSAGE, "code": "assistant_error"}, status.HTTP_502_BAD_GATEWAY)
    latency_ms = int((time.monotonic() - started) * 1000)

    raw_usage = result.get("usage")
    try:
        reconcile_budget(reservation, reported_total_tokens(raw_usage))
    except BudgetBackendUnavailable:
        logger.exception("Could not reconcile public-assistant reservation")
    # Only plausible integers are stored and returned: the raw block is provider-controlled.
    usage = sanitized_usage(raw_usage)
    reply = result.get("text", "")
    turn.log(AssistantMessageLog.STATUS_OK, reply=reply, token_usage=usage, latency_ms=latency_ms)
    return turn.respond({"available": True, "reply": reply, "usage": usage}, status.HTTP_200_OK)

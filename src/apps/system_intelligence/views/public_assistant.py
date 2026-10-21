"""Public, visitor-facing assistant API.

Endpoints (mounted at ``/assistant/``):
  - POST /assistant/chat/   -- tool-free, read-only chat
  - GET  /assistant/config/ -- public-safe display config

The chat path is graceful: when the assistant is disabled or the backing
AWS/model is not configured it returns HTTP 200 with ``available: false`` so
the frontend widget can render an unavailable state instead of erroring.

Limits are keyed on the ACTOR (see ``services/public_assistant/actors.py``),
never on the client IP: ``GET /assistant/config/`` hands the browser a signed
``visitor_token`` and the widget returns it in the chat request body. A chat
request without a usable one is still answered, in the shared ``legacy``
bucket, and its response carries a ``visitor_token`` for the client to store.
"""

import logging
import time
from dataclasses import dataclass

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.authn.security import SoftJWTAuthentication
from apps.core.models import AWSCredentialConfig
from apps.core.utils.throttle_cache import throttle_cache
from apps.system_intelligence.models import AssistantConversationLog, AssistantMessageLog, SystemIntelligenceConfig
from apps.system_intelligence.serializers import PublicAssistantChatSerializer
from apps.system_intelligence.services.bedrock import normalize_bedrock_model_id
from apps.system_intelligence.services.public_assistant import (
    FEATURE_ASSISTANT,
    KIND_LEGACY,
    VISITOR_FIELD,
    AssistantActor,
    BudgetBackendUnavailable,
    actor_token_limit,
    answer_public_question,
    build_public_context,
    client_ip,
    estimate_public_input_tokens,
    hash_ip,
    issue_visitor_token,
    reconcile_budget,
    release_budget,
    reported_total_tokens,
    reserve_budget,
    resolve_chat_actor,
    sanitized_usage,
)
from apps.system_intelligence.services.usage_log import log_assistant_turn

logger = logging.getLogger(__name__)

# Deliberately impersonal: the limit that was hit may be the assistant's global
# budget rather than the asker's own, so it must not blame the person asking.
_BUDGET_MESSAGE = "The assistant has reached its usage limit for now. Please try again later."
_ERROR_MESSAGE = "The assistant ran into a problem answering that. Please try again in a moment."
_BUDGET_UNAVAILABLE_MESSAGE = "The assistant is temporarily unavailable. Please try again in a moment."


class PublicAssistantActorThrottle(SimpleRateThrottle):
    """Request-rate limit per ACTOR (visitor / member / shared legacy bucket).

    Not keyed on the client IP: the whole campus shares one public address, so
    an IP bucket would let one classroom lock everybody out.

    This is a fairness limiter only. Its history lives in the bounded in-process
    ``throttle`` cache alias (see the ``cache`` attribute below): the effective
    rate is the nominal rate times the number of Uvicorn worker processes, and a
    restart forgets it.
    That is acceptable here because nothing about money depends on it -- spend
    is bounded by the PostgreSQL token budgets (per actor and global).
    """

    scope = "public_assistant"
    # NOT the default cache: the key is a visitor token anyone can mint, and in
    # the production file cache each minted key would be one more file slowing
    # down every cache write. The throttle alias is bounded and in-process, so
    # the rate is per Uvicorn worker (see apps.core.utils.throttle_cache).
    cache = throttle_cache
    # Callers without a usable visitor value (old cached bundles, scripts) all
    # share ONE bucket, so it is sized for many people rather than one.
    legacy_scope = "public_assistant_legacy"
    legacy_default_rate = "60/minute"

    def _rates(self) -> dict:
        # Read live from settings (THROTTLE_RATES is captured at import time,
        # which would ignore override_settings and runtime changes).
        return settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

    def get_rate(self):
        return self._rates()[self.scope]

    def allow_request(self, request, view):
        if resolve_chat_actor(request).kind == KIND_LEGACY:
            self.rate = self._rates().get(self.legacy_scope, self.legacy_default_rate)
            self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        actor = resolve_chat_actor(request)
        return self.cache_format % {"scope": self.scope, "ident": f"{actor.kind}:{actor.key}"}


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


class PublicAssistantConfigView(APIView):
    """GET /assistant/config/ -- public-safe display config only (never secrets)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        config = SystemIntelligenceConfig.load()
        starter_questions = config.public_assistant_starter_questions
        if not isinstance(starter_questions, list):
            starter_questions = []
        payload = {
            "enabled": config.public_assistant_enabled,
            "welcome_message": config.public_assistant_welcome_message,
            "starter_questions": starter_questions,
            "unavailable_message": config.public_assistant_unavailable_message,
            "max_message_chars": config.public_assistant_max_message_chars,
        }
        if config.public_assistant_enabled:
            # A fresh signed visitor identity for browsers that do not hold one
            # yet. Stateless: nothing is stored until the visitor spends tokens.
            payload[VISITOR_FIELD] = issue_visitor_token()
        response = Response(payload, status=status.HTTP_200_OK)
        # The body is per-visitor now; a shared cache must never replay it.
        response["Cache-Control"] = "no-store"
        return response


class PublicAssistantChatView(APIView):
    """POST /assistant/chat/ -- tool-free, read-only public chat."""

    permission_classes = [AllowAny]
    # The actor (member / visitor / shared legacy bucket) that keys every limit comes from ``request.user``: a valid
    # token keeps its member actor, a stale one is the visitor it is instead of getting a 401.
    authentication_classes = [SoftJWTAuthentication]
    throttle_classes = [PublicAssistantActorThrottle]

    def throttled(self, request, wait):
        """The framework's 429, plus the visitor value the client should store.

        A browser whose value has lapsed is rate-limited in the shared legacy
        bucket. If that bucket is saturated (a script, a crowd of old bundles),
        this is the only response the browser gets, so it must carry the
        replacement too: otherwise the browser could never leave the bucket.
        """
        exc = Throttled(wait)
        actor = resolve_chat_actor(request)
        if actor.replacement:
            exc.detail = {"detail": exc.detail, VISITOR_FIELD: actor.replacement}
        raise exc

    def post(self, request, *args, **kwargs):
        config = SystemIntelligenceConfig.load()

        # 1. Disabled -> graceful unavailable.
        if not config.public_assistant_enabled:
            return _unavailable_response(config)

        # 2. Validate payload (400 on failure).
        serializer = PublicAssistantChatSerializer(
            data=request.data,
            max_message_chars=config.public_assistant_max_message_chars,
            max_history_chars=config.public_assistant_max_history_chars,
        )
        serializer.is_valid(raise_exception=True)
        history = serializer.validated_data.get("history", [])
        history_limit = config.public_assistant_max_history_messages
        # The actor (visitor / member / shared legacy bucket) keys every limit. ip_hash is
        # recorded in the audit log only; it keys no limit. Both are resolved up front so
        # every terminal branch can audit and answer with them.
        turn = _ChatTurn(
            config=config,
            actor=resolve_chat_actor(request),
            message=serializer.validated_data["message"],
            session_id=serializer.validated_data.get("session_id", ""),
            # history[-0:] is the whole list, so handle a zero limit explicitly.
            history=history[-history_limit:] if history_limit else [],
            ip_hash=hash_ip(client_ip(request) or ""),
            model_id=normalize_bedrock_model_id(config.public_model_id) or "",
        )

        # 3. AWS / model not configured -> graceful unavailable.
        if not AWSCredentialConfig.load().is_configured or not turn.model_id:
            turn.log(AssistantMessageLog.STATUS_UNAVAILABLE)
            return _unavailable_response(config, turn.actor)

        prepared = _prepare_chat_input(turn)
        if isinstance(prepared, Response):
            return prepared
        context, estimated_input = prepared

        # 4. Atomically reserve estimated input + maximum output against BOTH
        #    the actor's budget and the assistant's global budget (the spend
        #    ceiling). The shared legacy actor has no per-actor token limit.
        reservation = _reserve_chat_budget(turn, estimated_input)
        if isinstance(reservation, Response):
            return reservation

        # 5. Invoke the tool-free model; 6. record usage and return.
        return _answer_and_settle(turn, context, reservation)


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

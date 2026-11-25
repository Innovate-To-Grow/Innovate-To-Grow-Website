"""The public assistant endpoints: its configuration, and a chat turn."""

from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.security import SoftJWTAuthentication
from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.models import AssistantMessageLog, SystemIntelligenceConfig
from apps.system_intelligence.serializers import PublicAssistantChatSerializer
from apps.system_intelligence.services.agents.providers import PUBLIC_ROLE, resolve_route, route_problem
from apps.system_intelligence.services.public_assistant import (
    VISITOR_FIELD,
    client_ip,
    hash_ip,
    issue_visitor_token,
    resolve_chat_actor,
)

from .chat_turn import _answer_and_settle, _ChatTurn, _prepare_chat_input, _reserve_chat_budget
from .responses import _unavailable_response
from .throttle import PublicAssistantActorThrottle


class PublicAssistantConfigView(APIView):
    """GET /assistant/config/ -- public-safe display config only (never secrets)."""

    rate_limit_scope = "public-background"

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

    rate_limit_scope = "ai"

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
        route = resolve_route(config, PUBLIC_ROLE)
        turn = _ChatTurn(
            config=config,
            actor=resolve_chat_actor(request),
            message=serializer.validated_data["message"],
            session_id=serializer.validated_data.get("session_id", ""),
            # history[-0:] is the whole list, so handle a zero limit explicitly.
            history=history[-history_limit:] if history_limit else [],
            ip_hash=hash_ip(client_ip(request) or ""),
            model_id=route.log_model_id,
        )

        # 3. Provider (AWS / API key) or model not configured -> graceful unavailable.
        if route_problem(route, aws_config=AWSCredentialConfig.load()):
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

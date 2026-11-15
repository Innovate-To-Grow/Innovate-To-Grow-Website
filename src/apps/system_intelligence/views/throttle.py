"""The per-actor rate limit of the public assistant (one visitor, one member, never the client IP)."""

from apps.core.services.request_limits.view_limits import PolicyRateThrottle, view_rate
from apps.core.utils.throttle_cache import throttle_cache
from apps.system_intelligence.services.public_assistant import (
    KIND_LEGACY,
    resolve_chat_actor,
)


class PublicAssistantActorThrottle(PolicyRateThrottle):
    """Request-rate limit per ACTOR (visitor / member / shared legacy bucket).

    Not keyed on the client IP: the whole campus shares one public address, so
    an IP bucket would let one classroom lock everybody out.

    This is a fairness limiter only. Its history lives in the bounded in-process
    ``throttle`` cache alias (see the ``cache`` attribute below): the effective
    rate is the nominal rate times the number of Uvicorn worker processes, and a
    restart forgets it.
    That is acceptable here because nothing about money depends on it -- spend
    is bounded by the PostgreSQL token budgets (per actor and global).

    Both rates are request-limit policies read live ("view-assistant-chat", 6/minute, and for the shared legacy
    bucket "view-assistant-legacy", 60/minute): staff edit them in the admin, and Smart limiting lowers them first
    under overload (AI is P3).
    """

    scope = "public_assistant"
    policy_scope = "view-assistant-chat"
    # NOT the default cache: the key is a visitor token anyone can mint, and in
    # the production file cache each minted key would be one more file slowing
    # down every cache write. The throttle alias is bounded and in-process, so
    # the rate is per Uvicorn worker (see apps.core.utils.throttle_cache).
    cache = throttle_cache
    # Callers without a usable visitor value (old cached bundles, scripts) all
    # share ONE bucket, so it is sized for many people rather than one.
    legacy_policy_scope = "view-assistant-legacy"

    def allow_request(self, request, view):
        if resolve_chat_actor(request).kind == KIND_LEGACY:
            self.rate = view_rate(self.legacy_policy_scope)
            self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        actor = resolve_chat_actor(request)
        return self.cache_format % {"scope": self.scope, "ident": f"{actor.kind}:{actor.key}"}

"""Who is asking: the actor that LLM budgets and request throttles are keyed on.

Never the client IP. Nearly every user of this site sits behind one campus
public address, so an IP-keyed limit is a single bucket for the whole campus.
Limits are keyed on one of three actors instead:

``member``
    An authenticated member (the past-project AI search, and the public chat if
    a caller ever authenticates). Real accounts are costly to mint.
``visitor``
    An anonymous browser holding a server-signed, stateless visitor value
    handed out by ``GET /assistant/config/`` and returned in the chat request
    body. Nothing is stored server-side; the signature alone proves that this
    server issued the random id.
``legacy``
    Everyone else: requests with a missing, malformed, expired or forged value
    (old cached frontend bundles, scripts). They are answered, never rejected,
    and all share ONE actor, so presenting self-made values can never buy a
    caller a bucket of their own. That one actor stands for many people at
    once, so it is NOT held to the per-actor token limit (see
    ``actor_token_limit``): it is bounded by its own request-rate throttle and
    by the public assistant's global budget.

Visitor values are free to obtain, so the per-actor limit is a fairness limit
only. The spend ceiling is the feature's global budget in ``budget.py``.
"""

import secrets
from collections.abc import Mapping
from dataclasses import dataclass

from django.core import signing
from django.utils.crypto import salted_hmac

KIND_MEMBER = "member"
KIND_VISITOR = "visitor"
KIND_LEGACY = "legacy"

# Request-body field carrying the signed visitor value (body, not a header, so
# the CORS allow-list needs no change).
VISITOR_FIELD = "visitor_token"

# A signed value is honoured for 30 days. Once it is older than half of that,
# the chat response hands back the same id re-signed, so an active browser
# keeps one identity (and one budget) without ever lapsing into ``legacy``.
VISITOR_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
VISITOR_RENEW_AFTER_SECONDS = 15 * 24 * 60 * 60

_SIGNING_SALT = "apps.system_intelligence.public_assistant.visitor"
_ACTOR_SALT = "apps.system_intelligence.public_assistant.actor"
_VISITOR_ID_BYTES = 16  # 128 random bits
_VISITOR_ID_HEX_CHARS = _VISITOR_ID_BYTES * 2
# A genuine signed value is ~110 characters. Anything much longer is not ours,
# and is not worth an HMAC computation.
_MAX_PRESENTED_CHARS = 512
_REQUEST_CACHE_ATTR = "_public_assistant_actor"


@dataclass(frozen=True)
class AssistantActor:
    """An identity limits are keyed on.

    ``key`` is 64 hex characters: it is the primary key of the actor's
    ``PublicAssistantTokenBudget`` row and the throttle ident. ``replacement``
    is a signed visitor value the client should store in place of whatever it
    sent (set when the presented one was unusable or is due for renewal).
    """

    kind: str
    key: str
    replacement: str | None = None


def _actor_key(label: str) -> str:
    """Keyed SHA-256 of an actor label, so budget rows never expose raw ids."""
    return salted_hmac(_ACTOR_SALT, label, algorithm="sha256").hexdigest()


def _sign(visitor_id: str) -> str:
    return signing.dumps({"v": visitor_id}, salt=_SIGNING_SALT)


def issue_visitor_token() -> str:
    """Mint a signed value around a fresh random 128-bit visitor id."""
    return _sign(secrets.token_hex(_VISITOR_ID_BYTES))


def _verified_visitor_id(presented: str, *, max_age: int) -> str | None:
    try:
        payload = signing.loads(presented, salt=_SIGNING_SALT, max_age=max_age)
    except Exception:  # noqa: BLE001 - any failure means "not a value we issued"
        # BadSignature / SignatureExpired are the expected cases. Anything else
        # (undecodable payload, odd input types) must degrade to the legacy
        # bucket too: a bad value may never turn into a 400 or a 500.
        return None
    if not isinstance(payload, dict):
        return None
    visitor_id = payload.get("v")
    if not isinstance(visitor_id, str) or len(visitor_id) != _VISITOR_ID_HEX_CHARS:
        return None
    return visitor_id


def member_actor(member_pk) -> AssistantActor:
    """Actor for an authenticated member (keyed on the member's UUID)."""
    return AssistantActor(kind=KIND_MEMBER, key=_actor_key(f"member:{member_pk}"))


def legacy_actor() -> AssistantActor:
    """The single shared actor for callers without a usable visitor value.

    It carries a freshly minted value: a current frontend stores it and has its
    own bucket from the next request on, while old bundles simply ignore it.
    """
    return AssistantActor(kind=KIND_LEGACY, key=_actor_key("legacy"), replacement=issue_visitor_token())


def actor_token_limit(actor: AssistantActor, configured_limit: int) -> int:
    """The per-actor token limit that applies to ``actor`` (``0`` = none).

    The legacy actor is exempt. It is every old-bundle browser and every
    token-less caller added together, so one visitor's allowance would be used
    up by the first couple of dozen answers of the day for all of them -- and
    it would protect nothing, because any caller can obtain a visitor value
    (and with it a full allowance of its own) for free. What bounds the legacy
    actor is its request-rate throttle and the public assistant's global
    budget, the only limit that actually caps spend.
    """
    if actor.kind == KIND_LEGACY:
        return 0
    return configured_limit


def visitor_actor(presented) -> AssistantActor:
    """Resolve a presented visitor value. Never raises; unusable -> legacy."""
    if not isinstance(presented, str) or not presented or len(presented) > _MAX_PRESENTED_CHARS:
        return legacy_actor()
    visitor_id = _verified_visitor_id(presented, max_age=VISITOR_RENEW_AFTER_SECONDS)
    if visitor_id is not None:
        return AssistantActor(kind=KIND_VISITOR, key=_actor_key(f"visitor:{visitor_id}"))
    visitor_id = _verified_visitor_id(presented, max_age=VISITOR_MAX_AGE_SECONDS)
    if visitor_id is not None:
        # Still valid but ageing: same id (same budget), fresh signature.
        return AssistantActor(
            kind=KIND_VISITOR,
            key=_actor_key(f"visitor:{visitor_id}"),
            replacement=_sign(visitor_id),
        )
    return legacy_actor()


def resolve_chat_actor(request) -> AssistantActor:
    """Actor for a public-assistant chat request, resolved once per request.

    The throttle and the view both need it, so the result is memoised on the
    request. Reading ``request.data`` may raise DRF's ``ParseError`` for a
    malformed body; that is left to propagate as the usual HTTP 400.
    """
    cached = getattr(request, _REQUEST_CACHE_ATTR, None)
    if cached is not None:
        return cached
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        actor = member_actor(user.pk)
    else:
        data = request.data
        actor = visitor_actor(data.get(VISITOR_FIELD) if isinstance(data, Mapping) else None)
    setattr(request, _REQUEST_CACHE_ATTR, actor)
    return actor

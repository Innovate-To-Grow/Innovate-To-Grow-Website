"""Who a request counts against.

- **Member**: a ``Bearer`` access token verified **offline** with SimpleJWT (signature, expiry, type, audience and
  issuer; no database query). An unverifiable token's claims are never read, so a forged ``member_uuid`` can
  neither drain another member's bucket nor dodge its own.
- **Admin user**: the session user ``AuthenticationMiddleware`` resolves, only when a session cookie is sent.
- **CLI token**: under the CLI prefix, a bearer that is not a JWT counts per SHA-256 of the token (the hash the CLI
  stores) in the ``cli`` scope. It is not verified here, so its caller still counts as a **source** (below), and every
  other scope ignores it: a made-up token per request never buys a fresh bucket.
- **Client IP**: ``apps.core.utils.client_ip`` with ``NUM_PROXIES`` (the trusted ALB hop in production).
- **Destination**: a key an app registers for a scope with ``register_identity_resolver`` (for example the hashed
  phone number of a code request), falling back to the member.

Each scope's ``identity`` picks one (see ``config/settings/base/integrations/request_limits/scopes.py``): sign-in
and code flows never fall back to the IP, because most users share one campus address.

A caller without a verified identity (no member token, no admin session) also has a **source**, its client IP. A
scope with a ``source_cap`` counts such callers per source too, as a flood ceiling only (``source_key``).
"""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import AccessToken

from apps.core.utils.client_ip import client_ip

from .runtime.context import section

logger = logging.getLogger(__name__)

_RESOLVERS: dict[str, Callable | str] = {}


@dataclass(frozen=True)
class Identity:
    member: str | None = None
    user: str | None = None
    cli: str | None = None
    ip: str | None = None

    @property
    def person(self) -> str | None:
        """The signed-in person (a verified member or the admin user), as a bucket key."""
        who = self.member or self.user
        return f"u:{who}" if who else None

    def key(self, kind: str, destination: str | None = None) -> str | None:
        """The bucket key for an identity ``kind``; None means only the scope's aggregate cap applies."""
        if kind == "member":
            return self.person
        if kind == "session":
            return f"u:{self.user}" if self.user else None
        if kind == "cli":
            return f"c:{self.cli}" if self.cli else self.person
        if kind == "destination":
            return f"d:{destination}" if destination else self.person
        if kind == "ip":
            return self.person or self.source
        return None

    @property
    def source(self) -> str | None:
        """The client IP of a caller without a verified identity, as a bucket key (None for a signed-in person)."""
        return None if self.person or not self.ip else f"ip:{self.ip}"


def register_identity_resolver(scope: str, resolver: Callable | str) -> None:
    """Count ``scope``'s requests per ``resolver(request)`` (a callable or its dotted path, returning a string or
    None). Call from ``AppConfig.ready()``."""
    _RESOLVERS[scope] = resolver


def _bearer(request) -> str | None:
    parts = request.META.get("HTTP_AUTHORIZATION", "").split()
    return parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else None


def _verified_member(raw: str) -> str | None:
    try:
        token = AccessToken(raw)
    except (TokenError, TypeError, ValueError):
        return None
    member = token.payload.get(jwt_settings.USER_ID_CLAIM)
    return str(member) if member else None


def _session_user(request) -> str | None:
    if settings.SESSION_COOKIE_NAME not in request.COOKIES:
        return None
    user = getattr(request, "user", None)
    return str(user.pk) if user is not None and user.is_authenticated else None


def resolve(request) -> Identity:
    """The request's identity (computed once per request)."""
    cached = getattr(request, "_request_limit_identity", None)
    if cached is not None:
        return cached
    raw = _bearer(request)
    member = _verified_member(raw) if raw else None
    cli = None
    if raw and member is None and request.path_info.startswith(section("fallback")["cli_prefix"]):
        cli = hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()
    identity = Identity(member=member, user=_session_user(request), cli=cli, ip=client_ip(request) or None)
    request._request_limit_identity = identity
    return identity


def destination(scope: str, request) -> str | None:
    resolver = _RESOLVERS.get(scope)
    if resolver is None:
        return None
    try:
        value = (import_string(resolver) if isinstance(resolver, str) else resolver)(request)
    except Exception:
        logger.warning("request_limits.identity_resolver_failed scope=%s", scope, exc_info=True)
        return None
    if not value:
        return None
    return hashlib.blake2b(str(value).encode(), digest_size=16).hexdigest()


def bucket_key(request, scope: str, kind: str) -> str | None:
    """The bucket key a request of ``scope`` (counted per ``kind``) uses, or None for the aggregate only."""
    found = destination(scope, request) if kind == "destination" else None
    return resolve(request).key(kind, found)


def source_key(request, key: str | None) -> str | None:
    """The source bucket of a caller without a verified identity, unless ``key`` already is that bucket."""
    source = resolve(request).source
    return None if source == key else source

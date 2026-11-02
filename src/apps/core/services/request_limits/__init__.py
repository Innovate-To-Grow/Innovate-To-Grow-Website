"""Request limits for every request the site answers (see ``config/settings/base/integrations/request_limits``).

``apps.core.middleware.RequestRateLimitMiddleware`` calls ``limiter``; apps plug in from ``AppConfig.ready()``:

- ``register_scope(view_name_or_view_path, scope)`` puts a route (often a third-party view) in a scope; a view of
  its own sets ``rate_limit_scope`` instead (a scope, or ``{"GET": scope, "*": scope}``);
- ``register_exemption(view_name_or_view_path, reason)`` never limits a route (``rate_limit_exempt`` on a view);
- ``register_identity_resolver(scope, resolver)`` counts a scope per a key the app derives from the request (the
  destination of a code request, say) instead of per member.

``rules/`` is pure (the limit precedence and the priority-ordered Smart controller); ``runtime/`` holds the
counters, heartbeats, the policy cache, signal windows, abuse escalation and the Smart state writes; ``status``
describes the live state for the admin.
"""

from .identity import register_identity_resolver
from .scopes import register_exemption, register_scope
from .status import counter_mode, runtime_status

__all__ = ["counter_mode", "register_exemption", "register_identity_resolver", "register_scope", "runtime_status"]

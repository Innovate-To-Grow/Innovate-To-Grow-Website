"""The request limiter: every request the site answers is limited by scope (see
``apps.core.services.request_limits``). It must run after ``CorsMiddleware`` (a 429 carries CORS headers, so the
browser can read it), after ``HealthCheckMiddleware`` (ALB probes are never limited), after ``SessionMiddleware``
and before ``CsrfViewMiddleware`` (its ``process_view`` decides before CSRF's, so a request refused for its CSRF token
is counted too); the ``core`` system checks refuse any other order. The admin user it reads is resolved by then:
every middleware's request phase, ``AuthenticationMiddleware``'s included, runs before any ``process_view``.

It decides in ``process_view``, after URL resolution, so it knows the route; requests for unmatched paths are
limited after their 404. Off when ``REQUEST_RATE_LIMITS_ENABLED`` is false (the test settings). A failure inside
the limiter is logged and lets the request through: the limiter never takes the site down with it.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class RequestRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.REQUEST_RATE_LIMITS_ENABLED:
            return self.get_response(request)
        from apps.core.services.request_limits import limiter

        try:
            response = self.get_response(request)
        except BaseException:
            limiter.release(request)
            raise
        try:
            return limiter.finish(request, response)
        except Exception:
            logger.exception("request_limits.finish_failed")
            limiter.release(request)
            return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not settings.REQUEST_RATE_LIMITS_ENABLED:
            return None
        from apps.core.services.request_limits import limiter

        try:
            return limiter.admit(request, view_func)
        except Exception:
            logger.exception("request_limits.admit_failed")
            limiter.release(request)
            return None

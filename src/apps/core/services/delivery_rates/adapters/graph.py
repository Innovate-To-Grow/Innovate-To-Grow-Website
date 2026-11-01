"""Microsoft Graph answers (``DELIVERY_RATES["signals"]["graph"]``): sendMail, mailbox reads and the token endpoint.

A throttle (429, 503, 509, with Retry-After as delta-seconds or an HTTP-date) stops the whole cooldown group,
because Outlook limits each app and mailbox across sends and reads. The innermost Graph error code is matched.
"""

from django.conf import settings

from ..rules.defaults import section, signal_patterns
from ..rules.signals import (
    RateSignal,
    Reason,
    blocked,
    code_in,
    none,
    ok,
    parse_retry_after,
    pause,
    quota,
    text_has,
    throttle,
    uncertain,
)


def retry_after(headers: dict) -> float | None:
    """Retry-After in seconds, clamped to [1, the smaller of PR #643's ``GRAPH_MAX_RETRY_AFTER_SECONDS`` and
    ``controller.retry_after_max_seconds``]; None when absent or unreadable."""
    ceiling = min(settings.GRAPH_MAX_RETRY_AFTER_SECONDS, section("controller")["retry_after_max_seconds"])
    return parse_retry_after(headers.get("retry-after"), maximum=ceiling)


def pushback(code: str) -> bool:
    """Exchange pushing back on a status other than a throttle: the message may have been accepted."""
    return code_in(code, signal_patterns("graph")["pause_codes"])


def graph_signal(status: int, headers: dict, code: str, *, read: bool = False, fresh_token: bool = False) -> RateSignal:
    """The signal of one Graph answer.

    For a send, a 403 or 404 means the app may not send as the mailbox, and a 401 for a token issued for this very
    send (``fresh_token``) means the credentials are refused: a breaker, so campaigns stop failing one by one until
    the configuration is fixed. A 401 for a cached token is only an expired token, refreshed on the next send. A
    mailbox read (``read``) is opened by staff, who need Microsoft's own refusal (or the missing message) each time,
    so it only answers for that request.
    """
    patterns = signal_patterns("graph")
    if status in (200, 202):
        return ok()
    if code_in(code, patterns["quota_codes"]):
        return quota("submission_quota")
    if status in patterns["throttle_statuses"]:
        return throttle("throttled", retry_after=retry_after(headers))
    if pushback(code):
        return pause("pushback", retry_after=retry_after(headers), uncertain=True)
    if status in patterns["mailbox_full_statuses"]:
        return blocked("mailbox_full")
    if read and status in (401, 403, 404):
        return none({401: "token_rejected", 403: "denied", 404: "not_found"}[status])
    if status in (403, 404):
        return blocked(Reason.PERMISSION)
    if status == 401 and fresh_token:
        return blocked(Reason.AUTH)
    if 400 <= status < 500:
        return none("rejected")
    return uncertain("server_error")


def token_signal(status: int, headers: dict, code: str, *, retryable: bool) -> RateSignal:
    """The signal of a failed token request: busy (pause Graph for the mailbox), else the credentials are refused."""
    if retryable or text_has(code, signal_patterns("graph")["token_pause_codes"]):
        return pause("token_endpoint", retry_after=retry_after(headers))
    return blocked(Reason.AUTH)

from apps.core.utils.client_ip import client_ip as resolve_client_ip


def client_ip(request):
    """Best-effort client IP for audit rows, resolved through ``NUM_PROXIES`` trusted hops.

    Delegates to ``apps.core.utils.client_ip`` so a caller cannot forge the recorded IP by prepending
    ``X-Forwarded-For`` entries behind the ALB. Returns ``None`` (never ``""``) when no address is available,
    which the nullable ``created_ip`` / ``request_ip`` columns store as NULL.
    """
    return resolve_client_ip(request) or None

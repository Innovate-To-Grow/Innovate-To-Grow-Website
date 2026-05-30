def client_ip(request):
    """Best-effort client IP for audit rows (first X-Forwarded-For hop, else REMOTE_ADDR)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None

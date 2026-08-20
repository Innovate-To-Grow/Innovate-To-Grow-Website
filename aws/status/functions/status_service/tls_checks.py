"""Bounded staff-visible TLS certificate checks for fixed monitored hosts."""

from __future__ import annotations

import socket
import ssl
from datetime import UTC, datetime

from .types import CheckResult


def run_tls_probe(check_id: str, hostname: str, timeout: float = 3.0) -> CheckResult:
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=timeout) as raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=hostname) as secure_socket:
                certificate = secure_socket.getpeercert()
        not_after = certificate.get("notAfter")
        if not not_after:
            return CheckResult(check_id, "tls", "unknown", "TLS_EXPIRY_UNKNOWN")
        expires_at = datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), tz=UTC)
        remaining_days = max(0, (expires_at - datetime.now(UTC)).days)
        detail = {"expiresAt": expires_at.isoformat().replace("+00:00", "Z"), "remainingDays": remaining_days}
        if remaining_days < 14:
            return CheckResult(check_id, "tls", "degraded", "TLS_EXPIRING_SOON", detail=detail)
        return CheckResult(check_id, "tls", "healthy", "TLS_VALID", detail=detail)
    except (OSError, ssl.SSLError, ValueError):
        # HTTP probes already determine public reachability; this is staff-only detail.
        return CheckResult(check_id, "tls", "unknown", "TLS_CHECK_FAILED")

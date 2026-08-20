"""Bounded DNS checks for fixed monitored hostnames without persisting IPs."""

from __future__ import annotations

from collections.abc import Callable

from .types import CheckResult


def _default_resolve(hostname: str, lifetime: float) -> bool:
    import dns.resolver

    answer = dns.resolver.resolve(hostname, "A", lifetime=lifetime, search=False)
    return bool(answer)


def run_dns_probe(
    check_id: str,
    hostname: str,
    timeout: float = 2.0,
    resolver: Callable[[str, float], bool] = _default_resolve,
) -> CheckResult:
    try:
        if not resolver(hostname, timeout):
            return CheckResult(check_id, "dns", "unhealthy", "DNS_NO_ANSWER")
        return CheckResult(check_id, "dns", "healthy", "DNS_RESOLVES")
    except Exception:
        # Do not persist resolver response text, nameserver addresses, or IPs.
        return CheckResult(check_id, "dns", "unknown", "DNS_CHECK_FAILED")

from __future__ import annotations

import json

from status_service.constants import COMPONENT_BY_ID, HttpProbeSpec
from status_service.dns_checks import run_dns_probe
from status_service.http_probes import run_http_probe


def transport(body: bytes, content_type: str = "application/json", status: int = 200):
    return lambda _url, _timeout: (status, body, content_type)


def test_homepage_requires_i2g_marker_and_html_content_type():
    spec = COMPONENT_BY_ID["production-website"].http_probes[0]

    healthy = run_http_probe(
        spec,
        transport=transport(
            b"<!doctype html><html><title>Innovate To Grow | School of Engineering</title></html>",
            "text/html",
        ),
    )
    generic = run_http_probe(
        spec,
        transport=transport(b"<!doctype html><html><title>Unrelated page</title></html>", "text/html"),
    )

    assert healthy.state == "healthy"
    assert generic.state == "unhealthy"
    assert generic.code == "HTML_MARKER_MISSING"


def test_health_probe_rejects_malformed_json_and_dependency_failure():
    spec = HttpProbeSpec("archive.ready", "https://archive.i2g.ucmerced.edu/readyz", "health")
    malformed = run_http_probe(spec, transport=transport(b"{bad json"))
    sheets_failure = run_http_probe(
        spec,
        transport=transport(json.dumps({"status": "error", "google_sheets": "unavailable"}).encode()),
    )

    assert malformed.code == "INVALID_HEALTH_JSON"
    assert sheets_failure.code == "HEALTH_NOT_OK"
    assert sheets_failure.state == "unhealthy"


def test_http_probes_require_exact_status_200():
    health = HttpProbeSpec("production-api.ready", "https://api.i2g.ucmerced.edu/readyz/", "health")
    page = COMPONENT_BY_ID["production-website"].http_probes[0]

    created = run_http_probe(
        health,
        transport=transport(b'{"status":"ok"}', status=201),
        attempts=1,
    )
    no_content = run_http_probe(
        page,
        transport=transport(b"<!doctype html><title>Innovate to Grow</title>", "text/html", status=204),
        attempts=1,
    )

    assert (created.state, created.code) == ("unhealthy", "HTTP_201")
    assert (no_content.state, no_content.code) == ("unhealthy", "HTTP_204")


def test_http_timeout_is_sanitized_and_retried():
    calls = 0

    def timeout(_url, _timeout):
        nonlocal calls
        calls += 1
        raise TimeoutError("secret endpoint details")

    result = run_http_probe(
        HttpProbeSpec("production-api.ready", "https://api.i2g.ucmerced.edu/readyz/", "health"),
        transport=timeout,
    )

    assert calls == 2
    assert result.code == "HTTP_TIMEOUT"
    assert "secret" not in repr(result)


def test_dns_probe_is_bounded_and_never_persists_ip_addresses():
    calls = []

    def resolver(hostname, lifetime):
        calls.append((hostname, lifetime))
        return True

    result = run_dns_probe("production-api.dns", "api.i2g.ucmerced.edu", resolver=resolver)

    assert result.state == "healthy"
    assert calls == [("api.i2g.ucmerced.edu", 2.0)]
    assert "address" not in result.detail


def test_dns_failure_is_sanitized_unknown():
    def resolver(_hostname, _lifetime):
        raise RuntimeError("10.0.0.1 secret resolver")

    result = run_dns_probe("demo-api.dns", "demo-api.i2g.ucmerced.edu", resolver=resolver)

    assert result.state == "unknown"
    assert result.code == "DNS_CHECK_FAILED"
    assert "10.0.0.1" not in repr(result)

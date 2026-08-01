#!/usr/bin/env python3
"""Render Amplify custom headers from validated deployment-time inputs."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlparse

HOST_RE = re.compile(
    r"^(?:\*\.)?[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$",
    re.IGNORECASE,
)


def origin(value: str, name: str) -> str:
    parsed = urlparse(value.strip())
    try:
        port = parsed.port
    except ValueError as exc:
        raise SystemExit(f"{name} contains an invalid port.") from exc
    hostname = parsed.hostname or ""
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or hostname.startswith("*.")
        or not HOST_RE.fullmatch(hostname)
    ):
        raise SystemExit(f"{name} must be an absolute HTTP(S) URL.")
    if parsed.username or parsed.password:
        raise SystemExit(f"{name} must not contain credentials.")
    rendered = f"{parsed.scheme}://{hostname.lower()}"
    if port is not None:
        rendered = f"{rendered}:{port}"
    return rendered


def parse_frame_sources(value: str) -> list[str]:
    """Return unique HTTPS origins safe for use as CSP source expressions."""
    sources: list[str] = []
    for token in re.split(r"[\s,]+", value.strip()):
        if not token:
            continue
        parsed = urlparse(token)
        try:
            port = parsed.port
        except ValueError as exc:
            raise SystemExit(f"Invalid frame source port in {token!r}.") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
            or not HOST_RE.fullmatch(parsed.hostname)
        ):
            raise SystemExit(f"Frame source must be an HTTPS origin without a path: {token!r}.")
        source = f"https://{parsed.hostname.lower()}"
        if port is not None:
            source = f"{source}:{port}"
        if source not in sources:
            sources.append(source)
    if not sources:
        raise SystemExit("AMPLIFY_CSP_FRAME_SOURCES must contain at least one HTTPS origin.")
    return sources


def build_csp(api_base_url: str, backend_proxy_url: str, frame_sources: str) -> str:
    api_origin = origin(api_base_url, "VITE_API_BASE_URL")
    backend_origin = origin(backend_proxy_url, "AMPLIFY_BACKEND_PROXY_URL")
    connect_origins = " ".join(dict.fromkeys((api_origin, backend_origin)))
    allowed_frames = " ".join(
        dict.fromkeys(
            (
                "'self'",
                "https://cdn.userway.org",
                *parse_frame_sources(frame_sources),
            )
        )
    )
    policy = " ".join(
        (
            "default-src 'self';",
            "base-uri 'self';",
            "object-src 'none';",
            "script-src 'self' https://cdn.userway.org https://siteimproveanalytics.com;",
            f"connect-src 'self' {connect_origins} https://cdn.userway.org https://siteimproveanalytics.com;",
            "img-src 'self' data: blob: https://cdn.userway.org https://siteimproveanalytics.com;",
            "font-src 'self' data: https://cdn.userway.org;",
            "style-src 'self' 'unsafe-inline' https://cdn.userway.org;",
            f"frame-src {allowed_frames};",
            "worker-src 'self' blob:;",
            "manifest-src 'self';",
            "form-action 'self';",
            "frame-ancestors 'self';",
            f"report-uri {backend_origin}/csp-report/;",
            "upgrade-insecure-requests;",
        )
    )
    script_directive = next(
        directive.strip() for directive in policy.split(";") if directive.strip().startswith("script-src")
    )
    if "'unsafe-inline'" in script_directive or "'unsafe-eval'" in script_directive:
        raise SystemExit("Inline or eval script execution must not be allowed.")
    return policy


def build_custom_headers(csp: str, mode: str) -> str:
    if mode not in {"report-only", "enforce"}:
        raise SystemExit("AMPLIFY_CSP_MODE must be report-only or enforce.")
    csp_header = "Content-Security-Policy" if mode == "enforce" else "Content-Security-Policy-Report-Only"
    return "\n".join(
        (
            "customHeaders:",
            "  - pattern: '**'",
            "    headers:",
            f"      - key: '{csp_header}'",
            f'        value: "{csp}"',
            "      - key: 'Referrer-Policy'",
            "        value: 'strict-origin-when-cross-origin'",
            "      - key: 'X-Content-Type-Options'",
            "        value: 'nosniff'",
            "      - key: 'Permissions-Policy'",
            "        value: 'camera=(), microphone=(), geolocation=()'",
            "",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--backend-proxy-url", required=True)
    parser.add_argument("--frame-sources", required=True)
    parser.add_argument("--mode", choices=("report-only", "enforce"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    csp = build_csp(args.api_base_url, args.backend_proxy_url, args.frame_sources)
    args.output.write_text(build_custom_headers(csp, args.mode), encoding="utf-8")


if __name__ == "__main__":
    main()

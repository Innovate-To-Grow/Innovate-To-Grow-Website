"""Pure rule transformation: backend-owned base rules plus CMS redirects merged into Amplify's list."""

from __future__ import annotations

from typing import Any

from .errors import AmplifyRedirectSyncError

_AMPLIFY_SPA_SOURCE = (
    r"</^[^.]+$|\.(?!(css|gif|ico|jpg|jpeg|js|png|txt|svg|webp|avif|"
    r"woff|woff2|ttf|otf|eot|map|json|xml|webmanifest)$)([^.]+$)/>"
)
_AMPLIFY_BASE_RULE_SOURCES = {
    "/sitemap.xml",
    "/api/<*>",
    "/admin",
    "/admin/<*>",
    "/static/<*>",
    "/media/<*>",
}
_AMPLIFY_LEGACY_SPA_SOURCES = {
    "/<*>",
    "/*",
    r"</^[^.]+$/>",
}


def _canonical_path(path: str) -> str:
    value = str(path or "").strip()
    if not value.startswith("/"):
        raise AmplifyRedirectSyncError("Amplify redirect paths must start with '/'.")
    return "/" if value == "/" else value.rstrip("/")


def amplify_source_variants(source_path: str) -> tuple[str, ...]:
    """Return exact canonical and trailing-slash variants for one source."""

    canonical = _canonical_path(source_path)
    if canonical == "/":
        return (canonical,)
    return canonical, f"{canonical}/"


def _managed_rules(redirects: list[dict[str, Any]]) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    seen_sources: set[str] = set()
    for redirect in sorted(redirects, key=lambda row: (row["source_path"], row["destination_path"])):
        target = _canonical_path(redirect["destination_path"])
        for source in amplify_source_variants(redirect["source_path"]):
            if source in seen_sources:
                continue
            seen_sources.add(source)
            rules.append({"source": source, "target": target, "status": "301"})
    return rules


# (Amplify source, backend path) rewrites, in rule order. Admin paths are proxied only when configured.
_BACKEND_PASSTHROUGH = (
    ("/sitemap.xml", "/sitemap.xml"),
    ("/api/<*>", "/<*>"),
)
_ADMIN_PASSTHROUGH = (
    ("/admin", "/admin/"),
    ("/admin/<*>", "/admin/<*>"),
    ("/static/<*>", "/static/<*>"),
    ("/media/<*>", "/media/<*>"),
)


def canonical_amplify_base_rules(
    *,
    backend_proxy_url: str,
    proxy_admin_paths: bool,
) -> list[dict[str, str]]:
    """Return the backend-owned passthrough rules and final SPA fallback."""

    backend_proxy_url = backend_proxy_url.rstrip("/")
    passthrough = _BACKEND_PASSTHROUGH + (_ADMIN_PASSTHROUGH if proxy_admin_paths else ())
    rules = [
        {"source": source, "target": f"{backend_proxy_url}{target_path}", "status": "200"}
        for source, target_path in passthrough
    ]
    rules.append({"source": _AMPLIFY_SPA_SOURCE, "target": "/index.html", "status": "200"})
    return rules


def _is_spa_fallback(rule: dict[str, Any]) -> bool:
    if not _targets_spa_index(rule):
        return False
    status = str(rule.get("status") or "").upper()
    source = str(rule.get("source") or "").strip()
    is_catch_all = source == _AMPLIFY_SPA_SOURCE or source in _AMPLIFY_LEGACY_SPA_SOURCES
    return is_catch_all and status in {"200", "404-200"}


def _targets_spa_index(rule: dict[str, Any]) -> bool:
    target = str(rule.get("target") or "").split("?", 1)[0].rstrip("/")
    return target in {"index.html", "/index.html"}


def _owns_edge_source(redirect: dict[str, Any]) -> bool:
    """Whether this row may replace or remove an existing edge rule."""

    return bool(redirect.get("is_active") or redirect.get("edge_rule_managed"))


def merge_amplify_rules(
    *,
    existing_rules: list[dict[str, Any]],
    all_redirects: list[dict[str, Any]],
    base_rules: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Build the desired rule list while preserving unrelated rule order."""

    owned_sources = {
        source
        for redirect in all_redirects
        if _owns_edge_source(redirect)
        for source in amplify_source_variants(redirect["source_path"])
    }
    active_redirects = [redirect for redirect in all_redirects if redirect["is_active"]]
    managed_rules = _managed_rules(active_redirects)
    if base_rules is not None:
        base_rules = [dict(rule) for rule in base_rules]
        base_fallbacks = [rule for rule in base_rules if _is_spa_fallback(rule)]
        if len(base_fallbacks) != 1:
            raise AmplifyRedirectSyncError("Canonical Amplify rules must contain exactly one SPA fallback.")
        base_passthroughs = [rule for rule in base_rules if not _is_spa_fallback(rule)]
        # All reserved passthrough sources belong to this reconciler, including
        # the optional admin rules when they are disabled. This lets a config
        # change remove the previously managed admin proxies deterministically.
        owned_sources.update(_AMPLIFY_BASE_RULE_SOURCES)
        unmanaged_rules = [
            dict(rule)
            for rule in existing_rules
            if str(rule.get("source") or "") not in owned_sources and not _is_spa_fallback(rule)
        ]
        # Exact CMS redirects must precede every preserved wildcard/regex
        # rule that could otherwise shadow them. Reserved base passthroughs
        # cannot collide because those paths are rejected as redirect sources.
        desired_rules = [*base_passthroughs, *managed_rules, *unmanaged_rules, *base_fallbacks]
        return desired_rules, len(active_redirects), len(managed_rules)

    unmanaged_rules = [dict(rule) for rule in existing_rules if str(rule.get("source") or "") not in owned_sources]

    fallback_index = next(
        (index for index, rule in enumerate(unmanaged_rules) if _is_spa_fallback(rule)),
        len(unmanaged_rules),
    )
    desired_rules = [
        *unmanaged_rules[:fallback_index],
        *managed_rules,
        *unmanaged_rules[fallback_index:],
    ]
    return desired_rules, len(active_redirects), len(managed_rules)

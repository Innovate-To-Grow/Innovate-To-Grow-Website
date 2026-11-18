"""Evaluate npm audit findings against the narrow temporary exception."""

from __future__ import annotations

from datetime import date
from typing import Any

from scripts.ci.dependencies.npm_audit_core import (
    EXCEPTIONS,
    AuditDataError,
    actionable_vulnerabilities,
    dev_only_nodes,
    release,
    root_advisories,
)


def vulnerability_exception_failures(
    name: str,
    vulnerability: dict[str, Any],
    vulnerabilities: dict[str, Any],
    lock_packages: dict[str, Any],
) -> tuple[list[str], set[str]]:
    try:
        roots = root_advisories(name, vulnerabilities)
    except AuditDataError as exc:
        return [f"{name}: {exc}"], set()

    unknown = sorted(advisory for advisory, _, _ in roots if advisory not in EXCEPTIONS)
    if unknown:
        return [f"{name}: unaccepted advisory source(s): {', '.join(unknown)}"], set()

    failures = dev_only_nodes(name, vulnerability, lock_packages)
    for advisory, source_package, affected_range in roots:
        exception = EXCEPTIONS[advisory]
        if source_package != exception.package:
            failures.append(f"{advisory}: expected source package {exception.package!r}, got {source_package!r}")
        if affected_range != exception.affected_range:
            failures.append(
                f"{advisory}: affected range changed from {exception.affected_range!r} to {affected_range!r}"
            )
    return failures, {advisory for advisory, _, _ in roots}


def accepted_exception_failures(
    advisory: str,
    vulnerabilities: dict[str, Any],
    lock_packages: dict[str, Any],
    latest_versions: dict[str, str],
    today: date,
) -> list[str]:
    exception = EXCEPTIONS[advisory]
    source = vulnerabilities.get(exception.package)
    if not isinstance(source, dict):
        return [f"{advisory}: source package {exception.package!r} is absent from the audit report"]

    failures = dev_only_nodes(exception.package, source, lock_packages)
    if source.get("isDirect") is not False:
        failures.append(f"{advisory}: {exception.package} is no longer strictly transitive")

    for node in source.get("nodes", []):
        locked = lock_packages.get(node)
        version = locked.get("version") if isinstance(locked, dict) else None
        if version != exception.reviewed_version:
            failures.append(
                f"{advisory}: reviewed {exception.package} {exception.reviewed_version}, found {version!r} at {node}"
            )

    latest = latest_versions.get(exception.package)
    if latest is None:
        failures.append(f"{advisory}: could not establish the latest {exception.package} release")
    elif release(latest) > release(exception.reviewed_version):
        failures.append(
            f"{advisory}: {exception.package} {latest} is now published; update the lockfile and remove the exception"
        )
    elif latest != exception.reviewed_version:
        failures.append(
            f"{advisory}: expected latest {exception.package} to be {exception.reviewed_version}, got {latest}"
        )

    if today > exception.expires_on:
        failures.append(f"{advisory}: exception expired on {exception.expires_on.isoformat()}")
    return failures


def exception_failures(
    report: dict[str, Any],
    lock: dict[str, Any],
    latest_versions: dict[str, str],
    today: date,
) -> tuple[list[str], set[str]]:
    vulnerabilities = report.get("vulnerabilities")
    lock_packages = lock.get("packages")
    if not isinstance(vulnerabilities, dict) or not isinstance(lock_packages, dict):
        raise AuditDataError("audit report or package-lock.json is missing its package map")

    failures: list[str] = []
    accepted: set[str] = set()
    for name, vulnerability in actionable_vulnerabilities(report).items():
        finding_failures, finding_advisories = vulnerability_exception_failures(
            name,
            vulnerability,
            vulnerabilities,
            lock_packages,
        )
        failures.extend(finding_failures)
        accepted.update(finding_advisories)

    for advisory in sorted(accepted):
        failures.extend(accepted_exception_failures(advisory, vulnerabilities, lock_packages, latest_versions, today))
    return failures, accepted

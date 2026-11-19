"""Parse npm audit data and define the temporary advisory policy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

AUDIT_LEVEL = "moderate"
SEVERITY = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
ADVISORY_ID = re.compile(r"(?:^|/)(GHSA-[a-z0-9-]+)$", re.IGNORECASE)
RELEASE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class AuditException:
    package: str
    reviewed_version: str
    affected_range: str
    expires_on: date
    reason: str


# GitHub reviewed GHSA-fc5q-39xc-vjpf on 2026-11-17 but lists no patched
# picomatch release. The lockfile's affected copies are build/test tools only;
# no application runtime accepts glob patterns through them. Keep this exception
# short-lived so a release or a changed dependency path fails CI for review.
EXCEPTIONS = {
    "GHSA-fc5q-39xc-vjpf": AuditException(
        package="picomatch",
        reviewed_version="4.0.7",
        affected_range="<=4.0.7",
        expires_on=date(2026, 12, 18),
        reason="No patched picomatch release exists; affected copies are dev-only frontend tooling.",
    )
}


class AuditDataError(ValueError):
    """npm returned an audit shape that cannot be evaluated safely."""


def release(version: str) -> tuple[int, int, int]:
    match = RELEASE.fullmatch(version)
    if match is None:
        raise AuditDataError(f"unsupported npm release {version!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def advisory_from_via(via: dict[str, Any]) -> tuple[str, str, str]:
    url = str(via.get("url", ""))
    match = ADVISORY_ID.search(url)
    if match is None:
        raise AuditDataError(f"advisory has no recognized GHSA URL: {url!r}")
    advisory = match.group(1)
    canonical_advisory = f"GHSA-{advisory.split('-', 1)[1].lower()}"
    return canonical_advisory, str(via.get("name", "")), str(via.get("range", ""))


def _root_advisories(
    package: str,
    vulnerabilities: dict[str, Any],
    trail: tuple[str, ...],
) -> set[tuple[str, str, str]]:
    if package in trail:
        return set()
    vulnerability = vulnerabilities.get(package)
    if not isinstance(vulnerability, dict):
        raise AuditDataError(f"npm audit references missing vulnerability {package!r}")
    via_entries = vulnerability.get("via")
    if not isinstance(via_entries, list) or not via_entries:
        raise AuditDataError(f"npm audit vulnerability {package!r} has no source advisory")

    roots: set[tuple[str, str, str]] = set()
    for via in via_entries:
        if isinstance(via, str):
            roots.update(_root_advisories(via, vulnerabilities, (*trail, package)))
        elif isinstance(via, dict):
            roots.add(advisory_from_via(via))
        else:
            raise AuditDataError(f"npm audit vulnerability {package!r} has an invalid `via` entry")
    return roots


def root_advisories(package: str, vulnerabilities: dict[str, Any]) -> set[tuple[str, str, str]]:
    roots = _root_advisories(package, vulnerabilities, ())
    if not roots:
        raise AuditDataError(f"npm audit vulnerability {package!r} has no root advisory after resolving dependencies")
    return roots


def actionable_vulnerabilities(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise AuditDataError("npm audit report has no vulnerability map")
    threshold = SEVERITY[AUDIT_LEVEL]
    actionable: dict[str, dict[str, Any]] = {}
    for name, vulnerability in vulnerabilities.items():
        if not isinstance(vulnerability, dict):
            raise AuditDataError(f"npm audit vulnerability {name!r} is not an object")
        severity = str(vulnerability.get("severity", ""))
        if severity not in SEVERITY:
            raise AuditDataError(f"npm audit vulnerability {name!r} has unknown severity {severity!r}")
        if SEVERITY[severity] >= threshold:
            actionable[str(name)] = vulnerability
    return actionable


def validate_audit_returncode(returncode: int, has_actionable_findings: bool, stderr: str = "") -> None:
    expected = 1 if has_actionable_findings else 0
    if returncode != expected:
        detail = f": {stderr.strip()}" if stderr.strip() else ""
        raise AuditDataError(f"npm audit exited {returncode}; expected {expected}{detail}")


def dev_only_nodes(name: str, vulnerability: dict[str, Any], lock_packages: dict[str, Any]) -> list[str]:
    nodes = vulnerability.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return [f"{name}: npm audit did not identify an installed node"]

    failures = []
    for node in nodes:
        package = lock_packages.get(node)
        if not isinstance(node, str) or not isinstance(package, dict):
            failures.append(f"{name}: {node!r} is absent from package-lock.json")
        elif package.get("dev") is not True:
            failures.append(f"{name}: {node} is not marked dev-only in package-lock.json")
    return failures

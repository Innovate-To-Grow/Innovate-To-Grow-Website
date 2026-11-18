#!/usr/bin/env python3
"""Run npm audit with narrow, expiring exceptions for unpatched dev tooling."""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 - runs npm with fixed, non-shell arguments
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PAGES = ROOT / "pages"
PACKAGE_LOCK = PAGES / "package-lock.json"
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


def run_json(command: list[str]) -> tuple[int, dict[str, Any], str]:
    result = subprocess.run(  # nosec B603 - fixed executable and arguments, shell=False
        command,
        cwd=PAGES,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise AuditDataError(f"{' '.join(command)} did not return JSON: {detail}") from exc
    if not isinstance(payload, dict):
        raise AuditDataError(f"{' '.join(command)} returned a non-object JSON payload")
    return result.returncode, payload, result.stderr


def newest_stable_version(package: str) -> str:
    result = subprocess.run(  # nosec B603 - fixed executable and arguments, shell=False
        ["npm", "view", package, "versions", "--json"],
        cwd=PAGES,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AuditDataError(f"npm view {package} versions failed: {result.stderr.strip() or 'no output'}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AuditDataError(f"npm view {package} versions returned invalid JSON") from exc

    versions = [payload] if isinstance(payload, str) else payload
    if not isinstance(versions, list) or not all(isinstance(version, str) for version in versions):
        raise AuditDataError(f"npm view {package} versions returned an unexpected payload")
    stable = [version for version in versions if RELEASE.fullmatch(version)]
    if not stable:
        raise AuditDataError(f"npm view {package} versions returned no stable release")
    return max(stable, key=release)


def main() -> int:
    try:
        returncode, report, stderr = run_json(["npm", "audit", f"--audit-level={AUDIT_LEVEL}", "--json"])
        if report.get("error"):
            raise AuditDataError(f"npm audit failed: {report['error']}")
        actionable = actionable_vulnerabilities(report)
        validate_audit_returncode(returncode, bool(actionable), stderr)
        if not actionable:
            print(f"npm audit found no {AUDIT_LEVEL}-or-higher vulnerabilities.")
            return 0

        lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
        source_packages = {
            exception.package
            for name in actionable
            for advisory, _, _ in root_advisories(name, report["vulnerabilities"])
            if (exception := EXCEPTIONS.get(advisory)) is not None
        }
        latest_versions = {package: newest_stable_version(package) for package in sorted(source_packages)}
        failures, accepted = exception_failures(
            report,
            lock,
            latest_versions,
            date.today(),
        )
    except (AuditDataError, json.JSONDecodeError, OSError) as exc:
        print(f"npm audit validation failed: {exc}", file=sys.stderr)
        return 1

    if failures:
        print("npm audit found findings that are not covered by a current narrow exception:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    for advisory in sorted(accepted):
        exception = EXCEPTIONS[advisory]
        print(
            f"::warning title=Temporary npm audit exception::{advisory} accepted through "
            f"{exception.expires_on.isoformat()}. {exception.reason}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

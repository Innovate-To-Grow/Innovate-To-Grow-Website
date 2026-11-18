#!/usr/bin/env python3
"""Run npm audit with narrow, expiring exceptions for unpatched dev tooling."""

from __future__ import annotations

import json
import subprocess  # nosec B404 - runs npm with fixed, non-shell arguments
import sys
from datetime import date
from pathlib import Path
from typing import Any

from scripts.ci.dependencies.npm_audit_core import (
    AUDIT_LEVEL,
    EXCEPTIONS,
    RELEASE,
    AuditDataError,
    actionable_vulnerabilities,
    release,
    root_advisories,
    validate_audit_returncode,
)
from scripts.ci.dependencies.npm_audit_policy import exception_failures

ROOT = Path(__file__).resolve().parents[3]
PAGES = ROOT / "pages"
PACKAGE_LOCK = PAGES / "package-lock.json"


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
        failures, accepted = exception_failures(report, lock, latest_versions, date.today())
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

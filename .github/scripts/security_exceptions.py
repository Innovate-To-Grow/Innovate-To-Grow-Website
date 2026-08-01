#!/usr/bin/env python3
"""Validate and render short-lived CI security-scan exceptions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

SCANNERS = {"pip-audit", "semgrep", "trivy"}
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{2,127}$")
MAX_EXCEPTION_DAYS = 90


def load_policy(path: Path, *, today: date | None = None) -> list[dict[str, str]]:
    today = today or date.today()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read security exception policy: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("security exception policy must be an object with schema_version 1")
    entries = payload.get("exceptions")
    if not isinstance(entries, list):
        raise ValueError("security exception policy exceptions must be a list")

    validated: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    required = {"scanner", "id", "owner", "rationale", "expires_on"}
    for index, entry in enumerate(entries):
        label = f"exceptions[{index}]"
        if not isinstance(entry, dict) or set(entry) != required:
            raise ValueError(f"{label} must contain exactly {sorted(required)}")
        if not all(isinstance(entry[field], str) for field in required):
            raise ValueError(f"{label} fields must all be strings")
        scanner = entry["scanner"]
        finding_id = entry["id"]
        if scanner not in SCANNERS:
            raise ValueError(f"{label}.scanner must be one of {sorted(SCANNERS)}")
        if not IDENTIFIER.fullmatch(finding_id):
            raise ValueError(f"{label}.id has an invalid format")
        if not entry["owner"].startswith("@") or len(entry["owner"]) < 3:
            raise ValueError(f"{label}.owner must be a GitHub user or team handle")
        if len(entry["rationale"].strip()) < 20:
            raise ValueError(f"{label}.rationale must contain at least 20 characters")
        try:
            expiry = date.fromisoformat(entry["expires_on"])
        except ValueError as exc:
            raise ValueError(f"{label}.expires_on must use YYYY-MM-DD") from exc
        if expiry <= today:
            raise ValueError(f"{label} expired on {expiry.isoformat()}")
        if expiry > today + timedelta(days=MAX_EXCEPTION_DAYS):
            raise ValueError(f"{label}.expires_on may be at most {MAX_EXCEPTION_DAYS} days away")
        key = (scanner, finding_id)
        if key in seen:
            raise ValueError(f"{label} duplicates {scanner} finding {finding_id}")
        seen.add(key)
        validated.append(entry)
    return validated


def arguments(entries: list[dict[str, str]], scanner: str) -> list[str]:
    flags = {
        "pip-audit": "--ignore-vuln",
        "semgrep": "--exclude-rule",
    }
    if scanner not in flags:
        raise ValueError("arguments output is supported only for pip-audit and semgrep")
    result: list[str] = []
    for entry in entries:
        if entry["scanner"] == scanner:
            result.extend([flags[scanner], entry["id"]])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy", type=Path)
    parser.add_argument(
        "--format",
        choices=["validate", "arguments", "ids"],
        default="validate",
    )
    parser.add_argument("--scanner", choices=sorted(SCANNERS))
    args = parser.parse_args()

    try:
        entries = load_policy(args.policy)
        if args.format == "arguments":
            if not args.scanner:
                raise ValueError("--scanner is required for arguments output")
            for value in arguments(entries, args.scanner):
                print(value)
        elif args.format == "ids":
            if not args.scanner:
                raise ValueError("--scanner is required for ids output")
            print(",".join(entry["id"] for entry in entries if entry["scanner"] == args.scanner))
        else:
            print(f"Validated {len(entries)} security exception(s).")
    except ValueError as exc:
        print(f"security exception policy error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

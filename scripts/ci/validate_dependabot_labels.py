#!/usr/bin/env python3
"""Fail preflight when Dependabot is configured to use labels that do not exist."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised in CI preflight
    raise SystemExit("PyYAML is required: python -m pip install PyYAML") from exc

ROOT = Path(__file__).resolve().parents[2]
DEPENDABOT = ROOT / ".github" / "dependabot.yml"


def configured_labels() -> set[str]:
    config = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
    labels: set[str] = set()
    for update in config.get("updates", []):
        labels.update(str(label) for label in update.get("labels", []))
    return labels


def existing_repo_labels(repo: str, token: str) -> set[str]:
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    labels: set[str] = set()
    page = 1
    while True:
        request = urllib.request.Request(
            f"{api_url}/repos/{repo}/labels?per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload:
            break
        labels.update(item["name"] for item in payload)
        page += 1
    return labels


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not repo:
        print("GITHUB_REPOSITORY is required.", file=sys.stderr)
        return 1
    if not token:
        print("GH_TOKEN or GITHUB_TOKEN is required.", file=sys.stderr)
        return 1

    wanted = configured_labels()
    existing = existing_repo_labels(repo, token)
    missing = sorted(wanted - existing)

    if missing:
        print("Dependabot references missing repository labels:", file=sys.stderr)
        for label in missing:
            print(f"  - {label}", file=sys.stderr)
        return 1

    print(f"Dependabot label config is valid: {', '.join(sorted(wanted))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

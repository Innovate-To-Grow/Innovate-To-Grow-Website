from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 - runs the pinned ruff binary with fixed arguments
from pathlib import Path

from .config import ROOT, Config
from .counting import Finding


def ruff_complexity(files: list[str], threshold: int) -> dict[tuple[str, str], int]:
    """Return {(path, function): mccabe score} for every function above ``threshold``."""
    ruff = shutil.which("ruff")
    if ruff is None:
        raise SystemExit("ruff is required on PATH to measure complexity (pip install ruff).")
    scores: dict[tuple[str, str], int] = {}
    for start in range(0, len(files), 400):
        chunk = files[start : start + 400]
        completed = subprocess.run(  # nosec B603 - fixed argv, no shell
            [
                ruff,
                "check",
                "--isolated",
                "--select",
                "C901",
                "--config",
                f"lint.mccabe.max-complexity={threshold}",
                "--output-format",
                "json",
                "--exit-zero",
                *chunk,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        for item in json.loads(completed.stdout or "[]"):
            message = item["message"]  # "`name` is too complex (17 > 10)"
            name = message.split("`")[1]
            score = int(message.rsplit("(", 1)[1].split(" ", 1)[0])
            rel = Path(item["filename"]).resolve().relative_to(ROOT).as_posix()
            scores[(rel, f"{name}@{item['location']['row']}")] = score
    return scores


def complexity_findings(files: list[str], config: Config) -> list[Finding]:
    by_profile: dict[str, list[str]] = {}
    for rel in files:
        profile = config.profile_for(rel)
        if profile.complexity:
            by_profile.setdefault(profile.name, []).append(rel)
    findings: list[Finding] = []
    for profile in config.profiles:
        if profile.name not in by_profile or not profile.complexity:
            continue
        advisory, hard = profile.complexity
        for (rel, located), score in ruff_complexity(by_profile[profile.name], advisory).items():
            name = located.split("@", 1)[0]
            findings.append(Finding("complexity", rel, name, score, advisory, hard))
    return findings

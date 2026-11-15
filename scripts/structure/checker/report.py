"""Render a structure ``Outcome`` as terminal text, GitHub job-summary Markdown, or JSON."""

from __future__ import annotations

import json
from collections import Counter

from scripts.structure.checker.config import RULES, Config
from scripts.structure.checker.rules import Outcome

TITLES = {
    "R001": "Files over {file_lines} lines",
    "R002": "Directories with more than {directory_files} files",
    "R003-mixed": "Directories mixing files and subdirectories",
    "R003-width": "Directories with more than {directory_subdirs} subdirectories",
    "R004-depth": "Files more than {module_depth} levels below their module (advisory)",
    "R004-name": "Directories named misc/others/temp",
}
MARKDOWN_LIST_LIMIT = 400


def title(rule: str, config: Config) -> str:
    return TITLES[rule].format(**vars(config.limits))


def counts(outcome: Outcome) -> dict[str, tuple[int, int]]:
    """``{rule: (active, excepted)}`` for every rule, in rule order."""
    active = Counter(finding.rule for finding in outcome.active)
    unique = {finding for findings in outcome.excepted.values() for finding in findings}
    excepted = Counter(finding.rule for finding in unique)
    return {rule: (active[rule], excepted[rule]) for rule in RULES}


def _stale_lines(outcome: Outcome) -> list[str]:
    lines = [f"stale exception (matches nothing): {entry.label}" for entry in outcome.stale_exceptions]
    lines += [f"stale unmeasured entry (matches no file): {entry.label}" for entry in outcome.stale_unmeasured]
    return lines


def render_text(outcome: Outcome, config: Config, mode: str, *, verbose: bool) -> str:
    lines = [f"Repository structure ({mode} mode)"]
    for rule, (active, excepted) in counts(outcome).items():
        lines.append(f"  {rule:<10} {active:5d} open, {excepted:4d} excepted  {title(rule, config)}")
    if verbose:
        lines += ["", *(finding.describe() for finding in outcome.active)]
    lines += _stale_lines(outcome)
    if mode == "report" and outcome.failing:
        lines.append("Report-only: findings do not fail this run (use --mode enforce to fail on them).")
    return "\n".join(lines)


def _markdown_findings(outcome: Outcome, config: Config) -> list[str]:
    lines = []
    for rule in RULES:
        findings = [finding for finding in outcome.active if finding.rule == rule]
        if not findings:
            continue
        lines += ["", f"<details><summary>{title(rule, config)}: {len(findings)}</summary>", "", "```"]
        lines += [finding.describe() for finding in findings[:MARKDOWN_LIST_LIMIT]]
        if len(findings) > MARKDOWN_LIST_LIMIT:
            lines.append(f"... {len(findings) - MARKDOWN_LIST_LIMIT} more (run the checker locally with --verbose)")
        lines += ["```", "</details>"]
    return lines


def render_markdown(outcome: Outcome, config: Config, mode: str) -> str:
    lines = [
        "## Repository structure",
        "",
        f"Mode: **{mode}**. Rules and exceptions: `scripts/structure/checker/structure.toml`.",
        "",
        "| Rule | Open | Excepted | Meaning |",
        "|---|---:|---:|---|",
    ]
    for rule, (active, excepted) in counts(outcome).items():
        lines.append(f"| {rule} | {active} | {excepted} | {title(rule, config)} |")
    lines += _markdown_findings(outcome, config)
    stale = _stale_lines(outcome)
    if stale:
        lines += ["", "**Stale entries**", "", *(f"- {line}" for line in stale)]
    return "\n".join(lines) + "\n"


def render_json(outcome: Outcome) -> str:
    def finding(item) -> dict:
        return {"rule": item.rule, "path": item.path, "value": item.value, "limit": item.limit}

    data = {
        "active": [finding(item) for item in outcome.active],
        "excepted": [
            {"entry": entry.label, "reason": entry.reason, "findings": [finding(item) for item in items]}
            for entry, items in outcome.excepted.items()
        ],
        "stale_exceptions": [entry.label for entry in outcome.stale_exceptions],
        "stale_unmeasured": [entry.label for entry in outcome.stale_unmeasured],
    }
    return json.dumps(data, indent=2) + "\n"

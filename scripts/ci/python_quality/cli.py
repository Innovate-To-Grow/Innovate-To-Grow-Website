#!/usr/bin/env python3
"""Report and enforce size / nesting / complexity limits for active Python code.

Counting rules (documented in docs/architecture/code-quality.md):

* A *logical line* is a physical line holding at least one code token. Blank
  lines, comment-only lines and docstring lines are not counted.
* File length = logical lines in the file.
* Function length = logical lines from the ``def`` line to the last line of the
  body, nested functions included (each nested function is also measured on its
  own). Decorators are not counted.
* Nesting depth = deepest stack of ``if/for/while/try/with/match`` blocks inside
  one function. ``elif`` and ``except``/``else``/``finally`` stay at the depth
  of the statement they belong to; a nested ``def``/``class`` starts again at 0.
* Complexity = Ruff's ``C901`` (mccabe) score, collected by running Ruff.
* Directory size = ``.py`` files directly inside one directory, ``__init__.py``
  excluded.

Each metric has an *advisory* threshold (reported, never fails) and a *hard*
threshold (fails unless the finding is listed in the exceptions file with a
written reason). Stale exceptions — entries that no longer match a finding —
also fail, so the list can only shrink.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from .complexity import complexity_findings
from .config import CONFIG_PATH, ROOT, Config, load_config
from .counting import Finding, analyze_source


def iter_python_files(config: Config) -> Iterator[str]:
    for root in config.roots:
        for path in sorted((ROOT / root).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if not config.is_excluded(rel):
                yield rel


def directory_findings(files: Iterable[str], config: Config) -> list[Finding]:
    counts: dict[str, int] = {}
    for rel in files:
        path = Path(rel)
        if path.name != "__init__.py":
            counts[path.parent.as_posix()] = counts.get(path.parent.as_posix(), 0) + 1
    advisory, hard = config.directory_files
    return [
        Finding("directory-files", directory, "", count, advisory, hard)
        for directory, count in sorted(counts.items())
        if count > advisory
    ]


def collect(config: Config) -> list[Finding]:
    files = list(iter_python_files(config))
    findings: list[Finding] = []
    for rel in files:
        findings.extend(analyze_source(rel, (ROOT / rel).read_text(encoding="utf-8"), config.profile_for(rel)))
    findings.extend(directory_findings(files, config))
    findings.extend(complexity_findings(files, config))
    return sorted(findings, key=lambda finding: (finding.metric, finding.path, finding.symbol))


def evaluate(findings: list[Finding], config: Config) -> tuple[list[Finding], list[str]]:
    """Return (hard findings without an exception, stale exception keys)."""
    hard_keys = {finding.key for finding in findings if finding.is_hard}
    unexcused = [finding for finding in findings if finding.is_hard and finding.key not in config.exceptions]
    stale = sorted(key for key in config.exceptions if key not in hard_keys)
    return unexcused, stale


def summarize(findings: list[Finding]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for finding in findings:
        bucket = summary.setdefault(finding.metric, {"advisory": 0, "hard": 0})
        bucket["hard" if finding.is_hard else "advisory"] += 1
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="also write every finding to this JSON file")
    parser.add_argument("--quiet", action="store_true", help="print only the summary and failures")
    args = parser.parse_args(argv)

    config = load_config()
    findings = collect(config)
    unexcused, stale = evaluate(findings, config)

    if not args.quiet:
        for finding in findings:
            excused = " (excepted)" if finding.is_hard and finding.key in config.exceptions else ""
            print(finding.describe() + excused)
    print("\nPython quality summary (advisory / hard):")
    for metric, counts in sorted(summarize(findings).items()):
        print(f"  {metric:16} {counts['advisory']:4} / {counts['hard']:3}")
    if args.json:
        payload = [finding.__dict__ | {"hard_violation": finding.is_hard} for finding in findings]
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for finding in unexcused:
        print(f"ERROR: {finding.describe()}  -> fix it or add `{finding.key}` to {CONFIG_PATH.name}")
    for key in stale:
        print(f"ERROR: stale exception `{key}` no longer exceeds its hard limit; remove it from {CONFIG_PATH.name}")
    return 1 if unexcused or stale else 0

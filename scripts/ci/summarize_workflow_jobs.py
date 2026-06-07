#!/usr/bin/env python3
"""Render a GitHub Actions jobs API response as a Markdown duration table."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    clean = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(clean)
    except ValueError:
        return None


def _format_duration(started_at: str | None, completed_at: str | None) -> str:
    start = _parse_time(started_at)
    end = _parse_time(completed_at)
    if start is None:
        return "n/a"
    if end is None:
        end = datetime.now(timezone.utc)
    total_seconds = max(0, int((end - start).total_seconds()))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _duration_seconds(job: dict[str, Any]) -> int:
    start = _parse_time(job.get("started_at"))
    end = _parse_time(job.get("completed_at"))
    if start is None or end is None:
        return -1
    return max(0, int((end - start).total_seconds()))


def _jobs_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        jobs = payload.get("jobs", [])
    elif isinstance(payload, list):
        jobs = payload
    else:
        jobs = []
    return [job for job in jobs if isinstance(job, dict)]


def render_markdown(payload: Any, limit: int = 30) -> str:
    jobs = _jobs_from_payload(payload)
    jobs.sort(key=lambda job: (_duration_seconds(job), job.get("name", "")), reverse=True)
    visible = jobs[:limit]

    lines = [
        "## CI Timing Report",
        "",
        f"Showing the {len(visible)} longest jobs from this workflow run.",
        "",
        "| Job | Conclusion | Duration | Started |",
        "|---|---|---:|---|",
    ]
    for job in visible:
        name = str(job.get("name") or "Unnamed job").replace("|", "\\|")
        conclusion = job.get("conclusion") or job.get("status") or "unknown"
        started_at = job.get("started_at") or "n/a"
        duration = _format_duration(job.get("started_at"), job.get("completed_at"))
        html_url = job.get("html_url")
        if html_url:
            name = f"[{name}]({html_url})"
        lines.append(f"| {name} | {conclusion} | {duration} | {started_at} |")

    if not visible:
        lines.append("| No jobs found | n/a | n/a | n/a |")

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args(argv)

    payload = json.load(sys.stdin)
    print(render_markdown(payload, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

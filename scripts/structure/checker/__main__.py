"""Command line: ``python -m scripts.structure.checker {report,migrations}`` from the repository root.

Exit codes: 0 = pass (or report-only), 1 = enforced findings or a changed existing migration,
2 = the configuration or the git range could not be read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.structure.checker.config import CONFIG_PATH, Config, ConfigError, load_config
from scripts.structure.checker.migrations import GuardError, run_guard
from scripts.structure.checker.report import render_json, render_markdown, render_text
from scripts.structure.checker.rules import apply_exceptions, evaluate
from scripts.structure.checker.tree import build_tree

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def run_report(args: argparse.Namespace, config: Config) -> int:
    tree = build_tree(args.root, config)
    outcome = apply_exceptions(evaluate(tree, config), tree, config)
    print(render_text(outcome, config, args.mode, verbose=args.verbose))
    if args.markdown:
        with open(args.markdown, "a", encoding="utf-8") as handle:
            handle.write(render_markdown(outcome, config, args.mode))
    if args.json:
        Path(args.json).write_text(render_json(outcome), encoding="utf-8")
    return 1 if args.mode == "enforce" and outcome.failing else 0


def run_migrations(args: argparse.Namespace, config: Config) -> int:
    return run_guard(args.root, args.base, args.head, config)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m scripts.structure.checker", description=__doc__)
    root.add_argument("--root", type=Path, default=REPOSITORY_ROOT, help="repository to check")
    root.add_argument("--config", type=Path, default=CONFIG_PATH, help="rules file (default: structure.toml)")
    commands = root.add_subparsers(dest="command", required=True)

    report = commands.add_parser("report", help="measure R001-R004 and print the findings")
    report.add_argument("--mode", choices=("report", "enforce"), default="report")
    report.add_argument("--verbose", action="store_true", help="list every open finding")
    report.add_argument("--markdown", metavar="PATH", help="append a Markdown summary (e.g. $GITHUB_STEP_SUMMARY)")
    report.add_argument("--json", metavar="PATH", help="write every finding as JSON")
    report.set_defaults(handler=run_report)

    guard = commands.add_parser("migrations", help="fail when an existing migration file changed")
    guard.add_argument("--base", default="", help="base commit (PR base, merge-group base, or push 'before')")
    guard.add_argument("--head", default="HEAD", help="head commit")
    guard.set_defaults(handler=run_migrations)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.handler(args, load_config(args.config))
    except (ConfigError, GuardError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

from .imports import ROOT, Import

CONFIG_PATH = ROOT / "scripts" / "ci" / "python_dependencies" / "python_dependencies.toml"


def app_of(module: str) -> str:
    return module.split(".")[1] if module.count(".") >= 1 else module


def load_config(path: Path = CONFIG_PATH) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def boundary_violations(imports: list[Import], config: dict) -> list[Import]:
    allowed: dict[str, list[str]] = config["allowed"]
    composition: list[str] = config.get("composition", [])
    violations = []
    for item in imports:
        source_app = app_of(item.source)
        if source_app == app_of(item.target) or _is_allowed(item.target, allowed.get(source_app, [])):
            continue
        if any(fnmatch.fnmatchcase(item.source, pattern) for pattern in composition):
            continue
        violations.append(item)
    return violations


def _is_allowed(target: str, entries: list[str]) -> bool:
    """An entry is an app label (``authn``) or a public module path inside it (``mail.services.tokens``)."""
    return any(target == f"apps.{entry}" or target.startswith(f"apps.{entry}.") for entry in entries)


def exception_matches(item: Import, entry: dict) -> bool:
    return fnmatch.fnmatchcase(item.source, entry["from"]) and (
        item.target == entry["to"] or item.target.startswith(entry["to"] + ".")
    )

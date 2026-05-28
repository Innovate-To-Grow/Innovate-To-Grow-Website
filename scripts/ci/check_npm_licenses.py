#!/usr/bin/env python3
"""Check package-lock licenses against the project's npm license allowlist."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ALLOWED_LICENSES = {
    "(MIT AND Zlib)",
    "(MIT OR GPL-3.0-or-later)",
    "(MPL-2.0 OR Apache-2.0)",
    "0BSD",
    "Apache-2.0",
    "BlueOak-1.0.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "CC-BY-4.0",
    "CC0-1.0",
    "ISC",
    "MIT",
    "MIT OR SEE LICENSE IN FEEL-FREE.md",
    "MIT-0",
    "MIT/X11",
    "MPL-2.0",
    "Python-2.0",
    "Unlicense",
}

MISSING_LICENSE_OVERRIDES = {
    "buffers": "MIT",
}


def package_name(lock_path: str, package: dict[str, object]) -> str:
    if "name" in package:
        return str(package["name"])
    marker = "node_modules/"
    if marker in lock_path:
        return lock_path.rsplit(marker, 1)[1]
    return lock_path or "<root>"


def normalized_license(raw_license: object, name: str) -> str | None:
    if isinstance(raw_license, str) and raw_license.strip():
        return raw_license.strip()
    return MISSING_LICENSE_OVERRIDES.get(name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-lock", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    lock = json.loads(args.package_lock.read_text(encoding="utf-8"))
    failures = []
    packages = []

    for lock_path, package in sorted((lock.get("packages") or {}).items()):
        if not lock_path:
            continue
        name = package_name(lock_path, package)
        license_name = normalized_license(package.get("license"), name)
        allowed = bool(license_name and license_name in ALLOWED_LICENSES)
        packages.append({"name": name, "path": lock_path, "license": license_name, "allowed": allowed})
        if not allowed:
            raw = package.get("license")
            failures.append(
                {
                    "name": name,
                    "path": lock_path,
                    "license": raw if raw is not None else "<missing>",
                }
            )

    report = {
        "package_count": len(packages),
        "allowlist": sorted(ALLOWED_LICENSES),
        "missing_license_overrides": MISSING_LICENSE_OVERRIDES,
        "failures": failures,
        "packages": packages,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if failures:
        print("Disallowed or missing npm package licenses:", file=sys.stderr)
        for failure in failures:
            print(
                f"  - {failure['name']} ({failure['path']}): {failure['license']}",
                file=sys.stderr,
            )
        return 1

    print(f"Checked {len(packages)} npm packages against the license allowlist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

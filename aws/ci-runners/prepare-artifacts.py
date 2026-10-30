#!/usr/bin/env python3
"""Download digest-pinned upstream Lambda releases and package the local guard."""

import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "v8.0.0"
DIGESTS = {
    "webhook.zip": "37f748c2a0a0fe5823f99c78bb037ac1960b80de259ed811b8a9cfe9908c34b9",
    "runners.zip": "3b30333f3105ec862d81f29e78e27210a3dae9feed827b765305e82e724be9ad",
    "runner-binaries-syncer.zip": "4d210e2258f845b55df438c566230b3dde3689ceffe1c0d1b852b108f45aa968",
}


def main():
    output = ROOT / ".artifacts"
    output.mkdir(exist_ok=True)
    for name, expected in DIGESTS.items():
        url = f"https://github.com/github-aws-runners/terraform-aws-github-runner/releases/download/{VERSION}/{name}"
        with urllib.request.urlopen(url, timeout=90) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f"Release checksum mismatch: {name}")
        (output / name).write_bytes(data)
    with zipfile.ZipFile(output / "guard.zip", "w", zipfile.ZIP_DEFLATED) as package:
        for path in sorted((ROOT / "guard").glob("*.mjs")):
            if not path.name.endswith(".test.mjs"):
                # Stable archive metadata avoids needless Lambda updates.
                entry = zipfile.ZipInfo(path.name, date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                package.writestr(entry, path.read_bytes())
    print(json.dumps({"release": VERSION, "artifacts": list(DIGESTS) + ["guard.zip"]}))


if __name__ == "__main__":
    main()

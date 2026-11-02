"""Load a target's deployment settings without exposing runtime credentials."""

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


def validated_config(payload):
    allowed = set(json.loads((ROOT / "aws/cicd/deploy-config-keys.json").read_text()))
    if not isinstance(payload, dict) or not payload or set(payload) - allowed:
        raise ValueError("Deployment configuration contains unsupported keys")
    for value in payload.values():
        if not isinstance(value, str) or any(c in value for c in ("\r", "\n", "\x00")):
            raise ValueError("Deployment configuration values must be single-line strings")
    return payload


def export_config(payload, destination):
    payload = validated_config(payload)
    # Public identifiers must not be masked: substring masks suppress action outputs
    # such as image URIs. Only legacy URL credentials need a secret mask here.
    for key, value in payload.items():
        if value and key == "REDIS_URL" and urlsplit(value).password:
            escaped = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::add-mask::{escaped}")
    with open(destination, "a", encoding="utf-8") as output:
        for key, value in payload.items():
            output.write(f"{key}={value}\n")
    print(f"Loaded {len(payload)} deployment settings from AWS")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"backend", "frontend", "archive"}:
        raise SystemExit("Expected deployment target: backend, frontend, or archive")
    result = subprocess.run(
        [
            "aws",
            "secretsmanager",
            "get-secret-value",
            "--region",
            "us-west-2",
            "--secret-id",
            f"itg/{sys.argv[1]}/deploy-config",
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise SystemExit("Cannot read AWS deployment configuration; verify role and secret permissions")
    payload = json.loads(json.loads(result.stdout)["SecretString"])
    export_config(payload, os.environ["GITHUB_ENV"])


if __name__ == "__main__":
    main()

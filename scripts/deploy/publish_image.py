"""Publish a commit tag once, returning a digest-pinned deployment URI."""

import argparse
import json
import os
import re
import subprocess


def existing_digest(repository, tag):
    result = subprocess.run(
        [
            "aws",
            "ecr",
            "describe-images",
            "--repository-name",
            repository,
            "--image-ids",
            f"imageTag={tag}",
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        if "(ImageNotFoundException)" in result.stderr:
            return None
        raise RuntimeError(result.stderr)
    digest = json.loads(result.stdout)["imageDetails"][0]["imageDigest"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("ECR returned an invalid image digest")
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("repository", "registry", "tag"):
        parser.add_argument(f"--{option}", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--context")
    source.add_argument("--source")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.tag):
        parser.error("A full commit SHA is required")
    target = f"{args.registry}/{args.repository}:{args.tag}"
    digest = existing_digest(args.repository, args.tag)
    if not digest:
        command = (
            ["docker", "build", "-t", target, args.context] if args.context else ["docker", "tag", args.source, target]
        )
        subprocess.run(command, check=True)
        subprocess.run(["docker", "push", target], check=True)
        digest = existing_digest(args.repository, args.tag)
    if not digest:
        raise RuntimeError("Published image could not be resolved")
    image = f"{args.registry}/{args.repository}@{digest}"
    print(image)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"image={image}\n")


if __name__ == "__main__":
    main()

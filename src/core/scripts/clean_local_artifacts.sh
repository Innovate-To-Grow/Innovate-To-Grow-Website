#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

rm -rf \
  "${REPO_ROOT}/.ruff_cache" \
  "${REPO_ROOT}/.idea" \
  "${REPO_ROOT}/pages/dist" \
  "${REPO_ROOT}/pages/node_modules"

find "${REPO_ROOT}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${REPO_ROOT}" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

rm -f \
  "${REPO_ROOT}/src/db.sqlite3" \
  "${REPO_ROOT}/src/.coverage"

echo "Removed local caches, build outputs, IDE metadata, and generated Python artifacts."

#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

# Install Python backend dependencies (cffi needed by system cryptography package)
pip install cffi -r "$PROJECT_DIR/src/requirements.txt"

# Install Node frontend dependencies
cd "$PROJECT_DIR/pages"
npm install

# Set Django settings for dev (SQLite, no external services needed)
echo 'export DJANGO_SETTINGS_MODULE="core.settings.dev"' >> "$CLAUDE_ENV_FILE"

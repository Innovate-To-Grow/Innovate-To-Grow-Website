#!/usr/bin/env bash
#
# Run the full Playwright e2e matrix against a locally-built backend, the way
# CI does it, without needing Docker or PostgreSQL.
#
# Background: most specs mock the API, but the "live" specs —
# pages/e2e/smoke/live.spec.ts and the Django-admin flow in pages/e2e/admin/
# — talk to a real backend. They only pass when that backend is configured the
# way CI configures it:
#   * config.settings.test  — its CORS allowlist includes the :4173 preview
#     origin (config.settings.local only allows the :5173 dev server)
#   * a migrated DB seeded with deterministic admin E2E data
#     (manage.py seed_admin_e2e --yes)
#   * `runserver --insecure` — serves the admin/Unfold statics that DEBUG=False
#     would otherwise 404
#
# This script points config.settings.test at a throwaway SQLite DB under src/
# (gitignored) so your dev database is untouched, and avoids the PostgreSQL
# service container CI uses.
#
# Usage:
#   scripts/e2e-local.sh [--fresh] [playwright test args...]
#
#   scripts/e2e-local.sh                            # full 10-project matrix
#   scripts/e2e-local.sh e2e/smoke/live.spec.ts     # a single spec file
#   scripts/e2e-local.sh --project=chromium         # one project
#
# Environment overrides:
#   PYTHON   Python interpreter with the Django deps installed
#            (default: src/.venv/bin/python)
#   E2E_DB   SQLite DB path (default: src/e2e.sqlite3)
#
# Ports 8000 (backend) and 4173 (frontend preview) must be free.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/src"
PAGES_DIR="$REPO_ROOT/pages"
BACKEND_URL="http://127.0.0.1:8000"

E2E_DB="${E2E_DB:-$SRC_DIR/e2e.sqlite3}"

FRESH=0
args=()
for arg in "$@"; do
  case "$arg" in
    --fresh) FRESH=1 ;;
    *) args+=("$arg") ;;
  esac
done

# Resolve a Python interpreter that has Django installed.
PYTHON="${PYTHON:-$SRC_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON" ]]; then
  echo "error: no Python interpreter found. Set PYTHON=/path/to/python." >&2
  exit 1
fi
if ! "$PYTHON" -c 'import django' >/dev/null 2>&1; then
  echo "error: $PYTHON does not have Django installed." >&2
  echo "       Install deps (e.g. create src/.venv and pip install -r src/requirements.txt)." >&2
  exit 1
fi

if [[ ! -d "$PAGES_DIR/node_modules" ]]; then
  echo "error: pages/node_modules is missing — run 'npm ci' in pages/ first." >&2
  exit 1
fi

backend_env=(
  "DJANGO_SETTINGS_MODULE=config.settings.test"
  "DB_ENGINE=django.db.backends.sqlite3"
  "DB_NAME=$E2E_DB"
  "ADMIN_REQUIRE_CONFIRMATION=true"
)

if [[ "$FRESH" == 1 ]]; then
  echo "==> Removing $E2E_DB"
  rm -f "$E2E_DB"
fi

echo "==> Migrating and seeding $E2E_DB (config.settings.test)"
(cd "$SRC_DIR" && env "${backend_env[@]}" "$PYTHON" manage.py migrate --noinput)
(cd "$SRC_DIR" && env "${backend_env[@]}" "$PYTHON" manage.py seed_admin_e2e --yes)

echo "==> Starting backend on $BACKEND_URL (runserver --insecure)"
(cd "$SRC_DIR" && exec env "${backend_env[@]}" "$PYTHON" manage.py runserver --insecure 127.0.0.1:8000 --noreload) &
backend_pid=$!

cleanup() {
  if [[ -n "${backend_pid:-}" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

ready=0
for _ in $(seq 1 120); do
  if curl -fsS "$BACKEND_URL/readyz/" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.5
done
if [[ "$ready" != 1 ]]; then
  echo "error: backend never became ready at $BACKEND_URL (is port 8000 free?)" >&2
  exit 1
fi

echo "==> Running Playwright (frontend preview on :4173)"
cd "$PAGES_DIR"
npx playwright test "${args[@]}"

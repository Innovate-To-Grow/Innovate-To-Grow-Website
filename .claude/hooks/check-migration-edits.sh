#!/bin/bash
# PreToolUse (Edit|Write): WARN — never block — when editing a migration that
# already exists on origin/main. Landed migrations must stay byte-stable because
# config/settings/_legacy_imports.py aliases legacy app imports that live inside
# them; the fix for a needed change is a NEW migration, not an edit. Brand-new
# migration files (not yet on main) pass silently.
#
# Non-blocking by design: this script always exits 0. It only emits a
# systemMessage so the warning shows at the moment the edit happens.

input=$(cat 2>/dev/null) || exit 0
command -v jq >/dev/null 2>&1 || exit 0

file_path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$file_path" ] || exit 0

# Only app migration modules; skip package __init__.py.
case "$file_path" in
  *src/apps/*/migrations/*.py) ;;
  *) exit 0 ;;
esac
case "$file_path" in */__init__.py) exit 0 ;; esac

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
case "$file_path" in
  "$root"/*) rel="${file_path#"$root"/}" ;;  # absolute, inside repo
  /*)        exit 0 ;;                         # absolute, outside repo — ignore
  *)         rel="$file_path" ;;               # already repo-relative
esac

# Prefer origin/main; fall back to local main. If neither exists, stay quiet.
ref="origin/main"
git rev-parse --verify --quiet "$ref" >/dev/null 2>&1 || ref="main"
git rev-parse --verify --quiet "$ref" >/dev/null 2>&1 || exit 0

if git cat-file -e "$ref:$rel" 2>/dev/null; then
  jq -n --arg f "$rel" --arg r "$ref" \
    '{systemMessage: ("\($f) already exists on \($r) — editing a landed migration breaks the legacy-import shim. Prefer a NEW migration (manage.py makemigrations). Proceeding without blocking.")}' \
    2>/dev/null
fi
exit 0

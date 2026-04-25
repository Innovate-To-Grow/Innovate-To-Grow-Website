#!/bin/bash
# Stop hook: lightweight CI on files changed since HEAD.
# Reports ruff (backend, scoped), eslint (frontend, scoped), and tsc
# (frontend, full project) as a one-line systemMessage. Non-blocking.

set +e
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

# Skip outside a git repo.
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Files changed vs HEAD (staged + unstaged), excluding deletions.
changed=$(git diff --name-only --diff-filter=AM HEAD 2>/dev/null)
[ -z "$changed" ] && exit 0

py_files=$(echo "$changed" | grep '^src/.*\.py$')
ts_files=$(echo "$changed" | grep -E '^pages/src/.*\.(ts|tsx)$')

[ -z "$py_files" ] && [ -z "$ts_files" ] && exit 0

results=()

if [ -n "$py_files" ]; then
  py_count=$(echo "$py_files" | wc -l | tr -d ' ')
  rel_py=$(echo "$py_files" | sed 's|^src/||' | tr '\n' ' ')
  if (cd src && ruff check $rel_py >/dev/null 2>&1); then
    results+=("ruff ✓ ${py_count}py")
  else
    results+=("ruff ✗ ${py_count}py")
  fi
fi

if [ -n "$ts_files" ]; then
  ts_count=$(echo "$ts_files" | wc -l | tr -d ' ')
  rel_ts=$(echo "$ts_files" | sed 's|^pages/||' | tr '\n' ' ')
  if (cd pages && npx --no-install eslint --max-warnings=0 $rel_ts >/dev/null 2>&1); then
    results+=("eslint ✓ ${ts_count}ts")
  else
    results+=("eslint ✗ ${ts_count}ts")
  fi
  if (cd pages && npx --no-install tsc --noEmit >/dev/null 2>&1); then
    results+=("tsc ✓")
  else
    results+=("tsc ✗")
  fi
fi

[ ${#results[@]} -eq 0 ] && exit 0

joined=$(IFS=' · '; echo "${results[*]}")
jq -n --arg msg "CI: $joined" '{systemMessage: $msg, suppressOutput: true}'

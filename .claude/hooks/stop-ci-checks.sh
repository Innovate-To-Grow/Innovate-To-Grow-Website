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

# Build arrays from newline-delimited file lists so paths with spaces or
# shell metacharacters (rare in this repo, but possible) don't get split
# or interpreted by the shell.
py_array=()
if [ -n "$py_files" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] && py_array+=("${line#src/}")
  done <<<"$py_files"
fi
ts_array=()
if [ -n "$ts_files" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] && ts_array+=("${line#pages/}")
  done <<<"$ts_files"
fi

# `npx --no-install <bin>` exits 1 when the binary is missing -- which
# looks identical to a real lint failure. This wrapper distinguishes the
# two cases so a missing toolchain shows as `skip` instead of `✗`.
run_with_npx() {
  local label="$1"; shift
  local out
  out=$(cd pages && npx --no-install "$@" 2>&1)
  local code=$?
  if [ $code -eq 0 ]; then
    echo "ok"
  elif echo "$out" | grep -qiE 'could not determine executable|not found|no such file'; then
    echo "skip"
  else
    echo "fail"
  fi
}

if [ ${#py_array[@]} -gt 0 ]; then
  py_count=${#py_array[@]}
  if (cd src && ruff check "${py_array[@]}" >/dev/null 2>&1); then
    results+=("ruff ✓ ${py_count}py")
  else
    results+=("ruff ✗ ${py_count}py")
  fi
fi

if [ ${#ts_array[@]} -gt 0 ]; then
  ts_count=${#ts_array[@]}
  case "$(run_with_npx eslint eslint --max-warnings=0 "${ts_array[@]}")" in
    ok)   results+=("eslint ✓ ${ts_count}ts") ;;
    skip) results+=("eslint ⊘ ${ts_count}ts") ;;
    *)    results+=("eslint ✗ ${ts_count}ts") ;;
  esac
  case "$(run_with_npx tsc tsc --noEmit)" in
    ok)   results+=("tsc ✓") ;;
    skip) results+=("tsc ⊘") ;;
    *)    results+=("tsc ✗") ;;
  esac
fi

[ ${#results[@]} -eq 0 ] && exit 0

joined=$(IFS=' · '; echo "${results[*]}")
jq -n --arg msg "CI: $joined" '{systemMessage: $msg, suppressOutput: true}'

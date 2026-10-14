#!/usr/bin/env bash
# Download the latest blob from each E2E project. GitHub Actions reruns can
# leave multiple artifacts with the same name in one run; the newest wins.
set -euo pipefail

: "${GITHUB_REPOSITORY:?}"
: "${GITHUB_RUN_ID:?}"

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
rm -rf pages/all-blob-reports
mkdir -p pages/all-blob-reports

gh api --paginate \
  "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/artifacts?per_page=100" \
  --jq '.artifacts[] | select(.name | startswith("blob-")) | [.name, (.id | tostring), .created_at, .digest] | @tsv' \
  > "$temporary/artifacts.tsv"

if [ ! -s "$temporary/artifacts.tsv" ]; then
  echo "::notice::No blob reports to merge; skipping report generation."
  exit 0
fi

LC_ALL=C sort -t $'\t' -k1,1 -k3,3r -k2,2nr "$temporary/artifacts.tsv" \
  | awk -F '\t' '!seen[$1]++' > "$temporary/latest.tsv"

while IFS=$'\t' read -r name artifact_id created_at digest; do
  if [[ ! "$name" =~ ^blob-[a-z0-9-]+$ ]] || [[ ! "$artifact_id" =~ ^[0-9]+$ ]] \
    || [[ ! "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "::error::Unexpected Playwright artifact metadata for $name."
    exit 1
  fi

  report="report-${name#blob-}.zip"
  for attempt in 1 2 3; do
    if gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts/${artifact_id}/zip" \
      > "$temporary/artifact.zip" \
      && printf '%s  %s\n' "${digest#sha256:}" "$temporary/artifact.zip" | sha256sum --check --status \
      && unzip -tqq "$temporary/artifact.zip"; then
      break
    fi
    if [ "$attempt" -eq 3 ]; then
      echo "::error::Unable to download and validate Playwright artifact $name."
      exit 1
    fi
    sleep 2
  done

  unzip -p "$temporary/artifact.zip" "$report" > "pages/all-blob-reports/$report"
  if ! unzip -tqq "pages/all-blob-reports/$report"; then
    echo "::error::Playwright blob report $report is invalid."
    exit 1
  fi
done < "$temporary/latest.tsv"

expected=$(wc -l < "$temporary/latest.tsv")
actual=$(find pages/all-blob-reports -maxdepth 1 -type f -name 'report-*.zip' | wc -l)
if [ "$actual" -ne "$expected" ]; then
  echo "::error::Expected $expected Playwright blob reports; found $actual."
  exit 1
fi

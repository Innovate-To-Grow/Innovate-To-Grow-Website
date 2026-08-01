#!/bin/sh
set -eu

python_version="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$python_version" != "3.11" ]; then
  echo "Python 3.11 is required to verify deployment locks (found $python_version)." >&2
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

common_args="
--generate-hashes
--resolver=backtracking
--strip-extras
--allow-unsafe
"

# Keep the generated header stable even though verification writes to /tmp.
export CUSTOM_COMPILE_COMMAND="./scripts/compile-requirements.sh"

# shellcheck disable=SC2086
python -m piptools compile --quiet $common_args \
  --output-file "$tmp_dir/production.lock.txt" \
  requirements/production.txt

# shellcheck disable=SC2086
python -m piptools compile --quiet $common_args \
  --output-file "$tmp_dir/local.lock.txt" \
  requirements/local.txt

diff -u requirements/production.lock.txt "$tmp_dir/production.lock.txt"
diff -u requirements/local.lock.txt "$tmp_dir/local.lock.txt"

#!/bin/sh
set -eu

python_version="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$python_version" != "3.11" ]; then
  echo "Python 3.11 is required to verify archive locks (found $python_version)." >&2
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
export CUSTOM_COMPILE_COMMAND="./compile-requirements.sh"

# Seed the temporary outputs with the committed locks so pip-compile reuses
# their versions, matching compile-requirements.sh. The diff then detects
# requirement input drift without failing merely because PyPI published a new
# version of an otherwise unconstrained transitive dependency.
cp requirements.txt "$tmp_dir/requirements.txt"
cp requirements-dev.txt "$tmp_dir/requirements-dev.txt"

# shellcheck disable=SC2086
python -m piptools compile --quiet $common_args \
  --output-file "$tmp_dir/requirements.txt" \
  requirements.in

# shellcheck disable=SC2086
python -m piptools compile --quiet $common_args \
  --output-file "$tmp_dir/requirements-dev.txt" \
  requirements-dev.in

diff -u requirements.txt "$tmp_dir/requirements.txt"
diff -u requirements-dev.txt "$tmp_dir/requirements-dev.txt"

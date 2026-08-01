#!/bin/sh
set -eu

python_version="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$python_version" != "3.11" ]; then
  echo "Python 3.11 is required to regenerate archive locks (found $python_version)." >&2
  exit 1
fi

python -m pip install --requirement ../../src/requirements/lock-tools.txt

common_args="
--generate-hashes
--resolver=backtracking
--strip-extras
--allow-unsafe
"

# shellcheck disable=SC2086
python -m piptools compile $common_args \
  --output-file requirements.txt \
  requirements.in

# shellcheck disable=SC2086
python -m piptools compile $common_args \
  --output-file requirements-dev.txt \
  requirements-dev.in

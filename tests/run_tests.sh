#!/bin/bash

# Only get real test names by filtering pytest output
pytest tests/legacy/test_registration.py --collect-only -q | grep '::' | while read test; do
  echo "🔹 Running $test"
  gtimeout 10s python3 -m pytest -v "$test"
done

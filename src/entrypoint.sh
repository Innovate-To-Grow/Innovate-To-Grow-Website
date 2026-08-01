#!/bin/sh
set -eu

# Container startup must be side-effect free. Database migrations and optional
# demo-admin bootstrap run as explicit, one-off ECS tasks in the deployment
# workflow before the web service is updated.
if [ "$#" -eq 0 ]; then
  echo "entrypoint: a process command is required" >&2
  exit 64
fi

exec "$@"

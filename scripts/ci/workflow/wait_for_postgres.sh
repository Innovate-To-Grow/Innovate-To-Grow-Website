#!/usr/bin/env bash
# Wait until a postgres container's real server accepts TCP connections.
#
# Usage: wait_for_postgres.sh CONTAINER USER DB [TIMEOUT_SECONDS]
#
# On first start the official postgres image runs initdb and its init scripts
# against a temporary server that listens only on the unix socket, stops it,
# and then starts the real server. A plain `pg_isready` goes through that
# socket, so it can pass during initialisation and the very next check can
# fail while the temporary server shuts down ("rejecting connections"). The
# temporary server never listens on TCP, so probe 127.0.0.1 inside the
# container and require two consecutive passes before calling it ready.
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "usage: $0 CONTAINER USER DB [TIMEOUT_SECONDS]" >&2
  exit 2
fi

container=$1
user=$2
db=$3
timeout=${4:-60}
if [[ ! "$timeout" =~ ^[1-9][0-9]*$ ]]; then
  echo "TIMEOUT_SECONDS must be a positive integer, got '$timeout'." >&2
  exit 2
fi

required_passes=2
passes=0
status="no probe ran"
deadline=$((SECONDS + timeout))

fail() {
  echo "::error::$1"
  echo "Last pg_isready result: $status"
  echo "----- docker logs $container -----"
  docker logs "$container" 2>&1 || true
  exit 1
}

while :; do
  state=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null) || state=missing
  if [ "$state" != "running" ]; then
    fail "PostgreSQL container $container is not running (state: $state)."
  fi

  if status=$(docker exec "$container" pg_isready -h 127.0.0.1 -p 5432 -U "$user" -d "$db" 2>&1); then
    passes=$((passes + 1))
    if [ "$passes" -ge "$required_passes" ]; then
      echo "PostgreSQL in $container accepts TCP connections: $status"
      exit 0
    fi
  else
    passes=0
  fi

  if [ "$SECONDS" -ge "$deadline" ]; then
    fail "PostgreSQL in $container did not accept TCP connections within ${timeout}s."
  fi
  sleep 1
done

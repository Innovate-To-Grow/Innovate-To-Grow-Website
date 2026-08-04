#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "${script_dir}/../.." && pwd)"
backend_dir="${repository_root}/src"
python_bin="${I2G_E2E_PYTHON:-${repository_root}/.venv/bin/python}"
postgres_image="${I2G_E2E_POSTGRES_IMAGE:-public.ecr.aws/docker/library/postgres:16}"
postgres_port="${I2G_E2E_DB_PORT:-55432}"
container_name="i2g-playwright-postgres-$$"
backend_pid=""

cleanup() {
  if [[ -n "${backend_pid}" ]]; then
    kill "${backend_pid}" >/dev/null 2>&1 || true
    wait "${backend_pid}" >/dev/null 2>&1 || true
  fi
  docker rm --force "${container_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if [[ ! -x "${python_bin}" ]]; then
  echo "Missing backend virtual environment at ${python_bin}." >&2
  echo "Create .venv at the repository root and install src/requirements/local.lock.txt first." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker is required for the ephemeral Playwright PostgreSQL database." >&2
  exit 1
fi

docker run \
  --detach \
  --rm \
  --name "${container_name}" \
  --publish "127.0.0.1:${postgres_port}:5432" \
  --env POSTGRES_DB=itg_e2e \
  --env POSTGRES_USER=itg_e2e_user \
  --env POSTGRES_PASSWORD=itg_e2e_pass \
  "${postgres_image}" >/dev/null

for _ in {1..60}; do
  if docker exec "${container_name}" pg_isready -U itg_e2e_user -d itg_e2e >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker exec "${container_name}" pg_isready -U itg_e2e_user -d itg_e2e >/dev/null 2>&1; then
  echo "The ephemeral PostgreSQL container did not become ready." >&2
  docker logs "${container_name}" >&2 || true
  exit 1
fi

export DJANGO_SETTINGS_MODULE=config.settings.test
export DB_NAME=itg_e2e
export DB_USER=itg_e2e_user
export DB_PASSWORD=itg_e2e_pass
export DB_HOST=127.0.0.1
export DB_PORT="${postgres_port}"
export ADMIN_REQUIRE_CONFIRMATION=true

cd "${backend_dir}"
"${python_bin}" manage.py migrate --noinput
"${python_bin}" manage.py seed_admin_e2e --yes
"${python_bin}" manage.py runserver --insecure 127.0.0.1:8000 &
backend_pid="$!"
wait "${backend_pid}"

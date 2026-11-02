#!/bin/sh
set -e

# Production migrations run once in the deployment workflow before rollout.
# Local Docker smoke tests can opt in explicitly against their disposable DB.
if [ "${RUN_DATABASE_MIGRATIONS:-false}" = "true" ]; then
    echo "Running database migrations..."
    python manage.py migrate --noinput
fi

# Both email and SMS challenge issuance require a signing key, including in
# observe mode. Initialize only missing keys, then check effective policy before
# accepting traffic. Explicit overrides and intentional pauses remain intact.
echo "Initializing send verification..."
python manage.py initialize_send_verification
python manage.py verify_service_configs --strict --send-verification-only --require-sms

case "${ENSURE_DEFAULT_ADMIN:-false}" in
  1|true|TRUE|yes|YES|on|ON)
    if [ -z "${DJANGO_SUPERUSER_EMAIL:-}" ]; then
      echo "ENSURE_DEFAULT_ADMIN is enabled but DJANGO_SUPERUSER_EMAIL is not set."
      exit 1
    fi
    if [ -z "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
      echo "ENSURE_DEFAULT_ADMIN is enabled but DJANGO_SUPERUSER_PASSWORD is not set."
      exit 1
    fi
    echo "Ensuring default admin account..."
    python manage.py ensure_default_admin \
      --yes \
      --email "$DJANGO_SUPERUSER_EMAIL" \
      --password-env DJANGO_SUPERUSER_PASSWORD \
      --first-name "${DJANGO_SUPERUSER_FIRST_NAME:-Demo}" \
      --last-name "${DJANGO_SUPERUSER_LAST_NAME:-Admin}"
    ;;
esac

# collectstatic is baked into the Docker image (see Dockerfile RUN step) so
# it no longer runs at boot. If the image was built without it (local dev,
# some CI paths), fall back to running it once here.
if [ ! -d "staticfiles" ] || [ -z "$(ls -A staticfiles 2>/dev/null)" ]; then
  echo "Collecting static files..."
  python manage.py collectstatic --noinput || echo "collectstatic failed (non-fatal)"
fi

echo "Starting Uvicorn..."
# Uvicorn's concurrency cap provides backpressure; hard per-request termination
# remains an ALB/deployment timeout concern.
exec uvicorn config.deploy.asgi:application \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout-graceful-shutdown "${UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN:-120}" \
  --limit-concurrency "${UVICORN_LIMIT_CONCURRENCY:-20}"

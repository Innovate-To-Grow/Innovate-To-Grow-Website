#!/bin/sh
set -e

# Migrations. NOTE: running this at every container boot on a multi-replica
# service can race on the django_migrations table. The medium-term plan is to
# move this to a dedicated pre-deploy job in the deploy workflow and then
# drop it from the runtime entrypoint.
echo "Running database migrations..."
python manage.py migrate --noinput

# collectstatic is baked into the Docker image (see Dockerfile RUN step) so
# it no longer runs at boot. If the image was built without it (local dev,
# some CI paths), fall back to running it once here.
if [ ! -d "staticfiles" ] || [ -z "$(ls -A staticfiles 2>/dev/null)" ]; then
  echo "Collecting static files..."
  python manage.py collectstatic --noinput || echo "collectstatic failed (non-fatal)"
fi

echo "Starting Gunicorn..."
exec gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 4 --threads 2 --timeout 120

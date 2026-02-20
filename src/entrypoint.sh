#!/bin/sh
set -e

echo "Waiting for database..."
python << END
import time, os, sys
import psycopg2
for i in range(30):
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get('DB_NAME', 'innovate_to_grow'),
            user=os.environ.get('DB_USER', 'user'),
            password=os.environ.get('DB_PASSWORD', 'password'),
            host=os.environ.get('DB_HOST', 'localhost'),
            port=os.environ.get('DB_PORT', '5432'),
            sslmode='require',
        )
        conn.close()
        print("Database is ready!")
        break
    except psycopg2.OperationalError as e:
        print(f"Database not ready, retrying ({i+1}/30)... Error: {e}")
        time.sleep(2)
    except Exception as e:
        print(f"Unexpected error connecting to database ({i+1}/30): {type(e).__name__}: {e}")
        time.sleep(2)
else:
    print("Could not connect to database after 30 attempts")
    sys.exit(1)
END

echo "Running migrations..."
python manage.py migrate --noinput

echo "Ensuring superuser exists and password is up to date..."
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py shell << 'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ["DJANGO_SUPERUSER_USERNAME"]
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
password = os.environ["DJANGO_SUPERUSER_PASSWORD"]

user, created = User.objects.get_or_create(
    username=username,
    defaults={
        "email": email,
        "is_staff": True,
        "is_superuser": True,
        "is_active": True,
    },
)

updated_fields = []
if email and user.email != email:
    user.email = email
    updated_fields.append("email")

if not user.is_staff:
    user.is_staff = True
    updated_fields.append("is_staff")

if not user.is_superuser:
    user.is_superuser = True
    updated_fields.append("is_superuser")

if not user.is_active:
    user.is_active = True
    updated_fields.append("is_active")

# Always sync password from env to support password rotation during deploy.
user.set_password(password)
updated_fields.append("password")

user.save()
action = "Created" if created else "Updated"
print(f"{action} superuser '{username}' ({', '.join(updated_fields)}).")
PY
else
    echo "DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD not set, skipping."
fi

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
exec "$@"

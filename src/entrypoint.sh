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
        )
        conn.close()
        print("Database is ready!")
        break
    except psycopg2.OperationalError:
        print(f"Database not ready, retrying ({i+1}/30)...")
        time.sleep(2)
else:
    print("Could not connect to database after 30 attempts")
    sys.exit(1)
END

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
exec "$@"

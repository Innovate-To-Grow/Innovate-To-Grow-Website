# Environment Notes

Common local variables live in `src/.env`.

## Frequently used values

```bash
DJANGO_SECRET_KEY=
DB_NAME=
DB_USER=
DB_PASSWORD=
REDIS_URL=
VITE_API_BASE_URL=
```

## Reminders

- Production deploys should remain environment-driven for infrastructure (Django, DB, Redis, S3 bucket, URLs).
- Service credentials (SES, SNS, Google Sheets, shared AWS IAM keys) live in the database under Django admin → Site Settings, not in `.env`. Run `python manage.py verify_service_configs --strict` before removing legacy env vars from a deployed environment.
- Do not hardcode secrets in code, fixtures, or docs.

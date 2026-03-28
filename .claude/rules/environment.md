# Environment Notes

Common local variables live in `src/.env`.

## Frequently used values

```bash
DJANGO_SECRET_KEY=
DB_NAME=
DB_USER=
DB_PASSWORD=
REDIS_URL=
GOOGLE_SHEETS_API_KEY=
VITE_API_BASE_URL=
```

## Reminders

- Production deploys should remain environment-driven.
- Do not hardcode secrets in code, fixtures, or docs.

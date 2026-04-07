# Operations

Maintenance tasks, data management, and operational guidance for administrators.

## Maintenance mode

### Enabling

The `SiteMaintenanceControl` model (`src/core/models/web.py`) controls maintenance mode:

1. In Django admin → Site Settings → Site Maintenance Control
2. Set `is_maintenance = True`
3. Optionally set a custom `message` and `bypass_password`
4. Save

### Behavior

- The `/health/` endpoint returns `{"maintenance": true}` in its response (still HTTP 200 for ALB)
- The frontend `HealthCheckProvider` detects this and shows the maintenance overlay
- The bypass password allows specific users to access the site during maintenance via `/maintenance/bypass/`

### Disabling

Set `is_maintenance = False` in the admin. The frontend polls every 10 seconds and will automatically recover.

## Database management

### Development reset

```bash
cd src && python manage.py resetdb --force
```

**Warning:** Destroys all data. Creates a fresh database with migrations applied and seeds a default admin user. Has safety guards — refuses to run against PostgreSQL in production-like settings.

### Migrations

```bash
cd src && python manage.py makemigrations    # Generate
cd src && python manage.py migrate           # Apply
```

**Critical rule:** Never edit a migration that has been merged to `main`. Create a new migration instead. The CI pipeline validates migrations against PostgreSQL to catch issues SQLite won't surface.

### Data fixtures

```bash
cd src && python manage.py loaddata cms/fixtures/footer_content.json
```

Load default footer content. Other fixtures may exist in app `fixtures/` directories.

## Service configuration

### Seeding from .env

```bash
cd src && python manage.py seed_service_configs
```

Creates `EmailServiceConfig` and `SMSServiceConfig` records from `.env` values. Useful for initial setup.

### Managing via admin

Singleton configuration models in Django admin → Site Settings:

| Model | Purpose | Key action |
|-------|---------|-----------|
| `EmailServiceConfig` | AWS SES or SMTP email credentials | Set active config |
| `SMSServiceConfig` | Twilio Verify API credentials | Set active config |
| `GoogleCredentialConfig` | Google service account JSON | Paste credentials JSON |
| `SiteMaintenanceControl` | Maintenance mode toggle | Enable/disable |

Only one of each can be active. Setting a new config as active deactivates the previous one.

## News sync

```bash
cd src && python manage.py sync_news --settings=core.settings.dev
```

Fetches articles from all configured `NewsFeedSource` records. Results logged in `NewsSyncLog`.

For production, this should be run on a schedule (cron or scheduled task).

## Event operations

### Registration sheet sync

From Event admin:
- **Automatic**: New registrations are synced to Google Sheets with 15-second debounce
- **Full replace**: Admin action to overwrite all sheet data with current database records

### Schedule import

From Event admin:
- Triggers schedule sync from Google Sheets
- Creates/updates `Semester`, `Project`, and schedule models

### Check-in

- Staff-only barcode scanning via `POST /event/check-in/scan/`
- Barcode format: `I2G|EVENT|{event_slug}|{ticket_code}`
- Check-in status dashboard: `GET /event/check-in/status/`

## Project import

Projects are imported via CSV in the Semester admin page. The CSV service (`src/projects/services/`) maps columns to `Project` model fields.

## Member operations

### Superuser creation

```bash
cd src && python manage.py createsuperuser
# Prompts for email (not username)

# Non-interactive:
cd src && python manage.py createsuperuser --email admin@example.com
```

### Member import/export

Available through the Member admin:
- Import from Excel (openpyxl)
- Export to Excel

## Monitoring

### Health check

`GET /health/` returns:
```json
{"status": "ok", "database": true, "maintenance": false}
```

Monitor the `database` field to detect connectivity issues.

### Sync logs

| Log model | Location in admin | Tracks |
|-----------|------------------|--------|
| `RegistrationSheetSyncLog` | Events section | Google Sheets sync success/failure |
| `NewsSyncLog` | CMS section | RSS feed sync results |
| `RecipientLog` | Mail section (inline) | Email delivery per recipient |

### Application logs

- **Local**: Console output from `python manage.py runserver`
- **Production**: CloudWatch at `/ecs/itg-backend` (us-west-2)

## Related pages

- [Django Admin](django-admin.md) — Admin interface navigation
- [Content Management](content-management.md) — CMS publishing workflow
- [Google Sheets: Operations](../integrations/google-sheets/operations.md) — Sheets-specific troubleshooting
- [Deployment: Environments](../deployment/environments.md) — Environment configuration

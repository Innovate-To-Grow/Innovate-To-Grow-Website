---
name: database
description: Use this skill when creating models, writing migrations, or working with the database layer.
---
# Database — Models and Migrations

## Environments

| Environment | Engine | Config |
|---|---|---|
| Dev | SQLite | `core.settings.dev` — zero-setup |
| CI | PostgreSQL 16 | `core.settings.ci` — GitHub Actions service |
| Prod | PostgreSQL + SSL | `core.settings.prod` — AWS RDS |

## Base Model

All domain models inherit from `core.models.ProjectControlModel`:

```python
# src/core/models/base/control.py
class ProjectControlModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    objects = ProjectControlManager()

    class Meta:
        abstract = True
```

## Available Mixins (`core.models.mixins`)

| Mixin | Fields | Notes |
|---|---|---|
| `AuthoredModel` | `created_by`, `updated_by` (FK to Member) | Uses `%(app_label)s_%(class)s_created` related_name |
| `OrderedModel` | `order` (PositiveIntegerField) | Meta ordering `["order"]` |
| `ActiveModel` | `is_active` (BooleanField, default True) | Indexed |

Compose: `class MyModel(ActiveModel, OrderedModel, ProjectControlModel):`

## Migrations

```bash
cd src && python manage.py makemigrations <app> --settings=core.settings.dev
cd src && python manage.py migrate --settings=core.settings.dev
```

- **NEVER** edit an existing migration that has landed on `main`. Create a new migration instead.
- CI validates with `makemigrations --check --dry-run` and `migrate --check`.
- Squash only if the migration count becomes unwieldy and after coordinating with the team.

## Cache Invalidation via Signals

Always wrap in `transaction.on_commit()` to avoid stale-cache races:

```python
# src/<app>/signals.py
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver([post_save, post_delete], sender=MyModel)
def invalidate_my_cache(sender, instance, **kwargs):
    transaction.on_commit(lambda: cache.delete("my:cache:key"))
```

Register signals in `AppConfig.ready()`:
```python
def ready(self):
    from . import signals  # noqa
```

See `src/cms/signals.py` for the canonical pattern.

## Singleton Models

Service config models (`EmailServiceConfig`, `GoogleCredentialConfig`, etc.) use the singleton pattern:
- Enforce `pk=1` in `save()`.
- Provide `load()` class method that returns the active instance.
- Located in `src/core/models/base/service_credentials.py`.

## Do NOT

- Use integer auto-increment primary keys — always UUID via `ProjectControlModel`.
- Edit migrations already merged to `main`.
- Query with `all_objects` unless you explicitly need soft-deleted rows.
- Forget `transaction.on_commit()` when invalidating cache in signals.
- Write raw SQL unless there is a clear performance need.
- Forget to add `db_index=True` on fields used in frequent lookups or filters.

## Key Files

- `src/core/models/base/control.py` — ProjectControlModel
- `src/core/models/managers/base.py` — ProjectControlManager, ProjectControlQuerySet
- `src/core/models/mixins/base.py` — AuthoredModel, OrderedModel, ActiveModel
- `src/core/models/base/service_credentials.py` — singleton config pattern
- `src/cms/signals.py` — canonical signal + cache invalidation
- `src/core/settings/dev.py` — SQLite config
- `src/core/settings/ci.py` — PostgreSQL CI config
- `src/core/settings/components/production.py` — PostgreSQL + SSL prod config

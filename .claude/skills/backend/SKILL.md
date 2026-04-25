---
name: backend
description: Use this skill when writing Django backend code — models, views, serializers, admin, services, or URLs under src/.
---
# Backend — Django / DRF Conventions

## Models

Inherit from `core.models.ProjectControlModel` (UUID PK, `created_at`, `updated_at`).
Mix in `AuthoredModel`, `OrderedModel`, or `ActiveModel` from `core.models.mixins` as needed.

```python
# src/<app>/models/<name>.py
from django.db import models
from core.models import ProjectControlModel
from core.models.mixins import ActiveModel, OrderedModel

class Widget(ActiveModel, OrderedModel, ProjectControlModel):
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name
```

- Place models in `src/<app>/models/` as a package; re-export from `__init__.py`.
- The default manager `objects` is `ProjectControlManager`.
- ForeignKey `on_delete`: use `CASCADE` or `SET_NULL` (with `null=True`).
- UUID path params: `<uuid:pk>`.

## Views

Use `rest_framework.views.APIView` with explicit HTTP method handlers.

```python
# src/<app>/views/<name>.py
from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

class WidgetListView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        cache_key = "widgets:list"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        data = WidgetSerializer(Widget.objects.all(), many=True).data
        cache.set(cache_key, data, timeout=300)
        return Response(data)
```

See `src/event/views/current_projects.py` for the canonical pattern.

## Serializers

```python
# src/<app>/serializers/<name>.py
from rest_framework import serializers

class WidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Widget
        fields = ["id", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
```

Always include `id`, `created_at`, `updated_at` in `read_only_fields`.

## Admin

Always inherit from `core.admin.BaseModelAdmin` (Unfold theme). Use `@admin.register`.

```python
# src/<app>/admin/<name>.py
from django.contrib import admin
from core.admin import BaseModelAdmin

@admin.register(Widget)
class WidgetAdmin(BaseModelAdmin):
    list_display = ("name", "is_active", "order", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "is_active", "order")}),
        ("System", {"classes": ["tab"], "fields": ("id", "created_at", "updated_at")}),
    )
```

For inlines use `unfold.admin.TabularInline` or `unfold.admin.StackedInline`.

## Services

Place business logic in `src/<app>/services/` — one file per concern.
Classes for complex operations, functions for simple utilities.
Use `@transaction.atomic` for multi-step DB operations.

## URLs

```python
# src/<app>/urls.py
from django.urls import path
from .views import WidgetListView

app_name = "widgets"
urlpatterns = [
    path("list/", WidgetListView.as_view(), name="widget-list"),
    path("<uuid:pk>/", WidgetDetailView.as_view(), name="widget-detail"),
]
```

Register in `src/core/urls.py` via `path("widgets/", include("widgets.urls"))`.

## Style

- Ruff: line-length 120, double quotes, LF, Python 3.11.
- Import order: stdlib, Django, DRF, third-party, first-party (`core`, `authn`, `cms`, `event`, etc.).
- Thin views — delegate to services and serializers.

## Do NOT

- Use ViewSets, generic API views, or DRF routers.
- Use stock `ModelAdmin` — always use `core.admin.BaseModelAdmin`.
- Set `DEFAULT_THROTTLE_CLASSES` globally (breaks tests at 127.0.0.1).
- Use integer auto-increment PKs — all models use UUID.
- Put heavy business logic in views — extract to `services/`.
- Edit an existing migration that has landed on `main`.

## Key Files

- `src/core/models/base/control.py` — ProjectControlModel
- `src/core/models/mixins/base.py` — AuthoredModel, OrderedModel, ActiveModel
- `src/core/admin/base.py` — BaseModelAdmin, ReadOnlyModelAdmin
- `src/core/admin/mixins.py` — TimestampedAdminMixin, ImportExportMixin, ExportMixin
- `src/event/views/current_projects.py` — canonical view pattern
- `src/event/urls.py` — canonical URL patterns
- `src/authn/services/` — service layer examples
- `pyproject.toml` — Ruff configuration

# Task: Unified Page Admin System

Execute all steps below in order. Read the referenced files before editing. Run tests/checks after each phase. Do NOT skip steps.

## Context

This is a Django 4.2 + React 19 + TypeScript project. Backend is in `src/`, frontend is in `pages/`.

- **HomePage** and **Page** must have identical capabilities (workflow, versioning, components, admin actions, Live Preview). The only difference is usage: HomePage = Home landing page (`name`, `is_active`); Page = other CMS pages (`slug`, `title`).
- Currently HomePage duplicates workflow logic that already exists in `WorkflowPublishingMixin`. We unify them.
- PageComponent types are restricted to 4: HTML, Markdown, Form, Table.
- `page` and `home_page` FK on PageComponent must NOT be editable on the standalone PageComponent admin.
- Admin UI (templates, CSS, JS) must be shared between HomePage and Page.
- Live Preview must match frontend rendering exactly.

---

## Phase 1: Model Unification

### Step 1.1: Add ComponentPageMixin

Read `src/pages/models/pages/mixins.py`. At the end of the file, add:

```python
class ComponentPageMixin(models.Model):
    """Shared component-ordering logic for Page and HomePage."""

    class Meta:
        abstract = True

    @property
    def ordered_components(self):
        """Return enabled components ordered for rendering."""
        return self.components.filter(is_enabled=True).order_by("order", "id")

    @property
    def all_components(self):
        """Return all components (including disabled) ordered."""
        return self.components.order_by("order", "id")
```

### Step 1.2: Export ComponentPageMixin

Read `src/pages/models/pages/__init__.py`. Add `ComponentPageMixin` to the imports from `.mixins` and to `__all__`.

### Step 1.3: Refactor HomePage model

Read `src/pages/models/pages/home_page.py` and `src/pages/models/pages/mixins.py` (WorkflowPublishingMixin).

Change HomePage to inherit from `ComponentPageMixin, WorkflowPublishingMixin, AuthoredModel, ProjectControlModel`. Import the needed classes:

```python
from core.models import AuthoredModel, ProjectControlModel
from .mixins import ComponentPageMixin, WorkflowPublishingMixin
```

Remove from HomePage:
- The inner class `PublishStatus` (use WorkflowPublishingMixin's)
- Fields: `status`, `published_at`, `published_by`, `submitted_for_review_at`, `submitted_for_review_by` (all come from WorkflowPublishingMixin now)
- Methods: `submit_for_review()`, `publish()`, `reject_review()` (come from mixin)
- Property: `published` (comes from mixin)
- Properties: `ordered_components`, `all_components` (come from ComponentPageMixin)

Keep on HomePage:
- `name`, `is_active` fields
- `save()` method (validation + deactivate others + cache invalidation)
- `delete()` method (cache)
- `get_active()` classmethod
- `__str__()` method

Override `unpublish()` to also deactivate:

```python
def unpublish(self, user=None):
    """Revert to Draft and deactivate."""
    super().unpublish(user=user)
    self.is_active = False
    self.save(update_fields=["is_active", "updated_at"])
```

### Step 1.4: Refactor Page model

Read `src/pages/models/pages/page.py`. Add `ComponentPageMixin` to the import from `.mixins` and to the class bases:

```python
from .mixins import AnalyticsFieldsMixin, ComponentPageMixin, SEOFieldsMixin, WorkflowPublishingMixin

class Page(SEOFieldsMixin, AnalyticsFieldsMixin, ComponentPageMixin, WorkflowPublishingMixin, AuthoredModel, ProjectControlModel):
```

Remove the local `ordered_components` and `all_components` property definitions from the Page class (they now come from ComponentPageMixin).

### Step 1.5: Update ComponentType

Read `src/pages/models/pages/page_component.py`. Change `ComponentType`:

```python
class ComponentType(models.TextChoices):
    HTML = "html", "HTML"
    MARKDOWN = "markdown", "Markdown"
    FORM = "form", "Form"
    TABLE = "table", "Table"
```

Remove `TEMPLATE` and `WIDGET`. In the `clean()` method, remove any validation specific to `TEMPLATE` or `WIDGET` if present. The existing HTML and FORM validations stay as-is.

### Step 1.6: Create migrations

Run:

```bash
cd src && python manage.py makemigrations pages
```

This should generate a migration covering:
- HomePage field changes (fields now come from mixins; related_name changes on FKs)
- HomePage new fields from AuthoredModel (created_by, updated_by)
- ComponentType choices update

Then create a data migration to convert existing `template`/`widget` component_type values to `html`:

```bash
cd src && python manage.py makemigrations pages --empty -n convert_component_types
```

Edit the generated empty migration to add:

```python
from django.db import migrations

def convert_old_types(apps, schema_editor):
    PageComponent = apps.get_model("pages", "PageComponent")
    PageComponent.objects.filter(component_type__in=["template", "widget"]).update(component_type="html")

def noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ("pages", "<previous_migration>"),
    ]
    operations = [
        migrations.RunPython(convert_old_types, noop),
    ]
```

Replace `<previous_migration>` with the actual previous migration name.

Run `cd src && python manage.py migrate` to apply.

Run `cd src && python manage.py test` to verify no breakage.

---

## Phase 2: Admin Unification

### Step 2.1: Create WorkflowAdminMixin

Create new file `src/pages/admin/base.py`:

```python
import json

from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from ..models import PageComponent


class CompactComponentInline(TabularInline):
    """Compact inline showing only summary fields. Users click Edit to open full editor."""

    model = PageComponent
    extra = 0
    fields = ("name", "component_type", "order", "is_enabled")
    ordering = ("order", "id")
    show_change_link = True


class WorkflowAdminMixin:
    """Shared admin logic for Page and HomePage."""

    def get_display_name(self, obj):
        return getattr(obj, "name", None) or getattr(obj, "title", "Unknown")

    def status_badge(self, obj):
        colors = {"draft": "#6c757d", "review": "#f0ad4e", "published": "#5cb85c"}
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{}; color:white; padding:3px 10px; '
            'border-radius:12px; font-size:11px; font-weight:500;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def component_count(self, obj):
        return obj.components.count()

    component_count.short_description = "Components"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            obj.save_version(comment=f"Edited via admin by {request.user}", user=request.user)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj:
            extra_context["versions"] = obj.get_versions()[:20]
            extra_context["current_status"] = obj.status
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def response_change(self, request, obj):
        name = self.get_display_name(obj)

        if "_submit_for_review" in request.POST:
            try:
                obj.submit_for_review(user=request.user)
                self.message_user(request, f'"{name}" submitted for review.', messages.SUCCESS)
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_publish" in request.POST:
            try:
                obj.publish(user=request.user)
                self.message_user(request, f'"{name}" has been published.', messages.SUCCESS)
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_unpublish" in request.POST:
            obj.unpublish(user=request.user)
            self.message_user(request, f'"{name}" has been unpublished.', messages.WARNING)
            return HttpResponseRedirect(request.path)

        if "_reject_review" in request.POST:
            try:
                obj.reject_review(user=request.user)
                self.message_user(request, f'"{name}" review rejected.', messages.WARNING)
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_rollback" in request.POST:
            version_number = request.POST.get("_rollback")
            if version_number:
                try:
                    obj.rollback(int(version_number), user=request.user)
                    self.message_user(request, f'"{name}" rolled back to version {version_number}.', messages.SUCCESS)
                except ValueError as e:
                    self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        return super().response_change(request, obj)

    @admin.action(description="Submit selected drafts for review")
    def action_submit_for_review(self, request, queryset):
        count = 0
        for obj in queryset.filter(status="draft"):
            try:
                obj.submit_for_review(user=request.user)
                count += 1
            except ValueError:
                pass
        self.message_user(request, f"{count} item(s) submitted for review.", messages.SUCCESS)

    @admin.action(description="Publish selected items")
    def action_publish(self, request, queryset):
        count = 0
        for obj in queryset.filter(status__in=["review", "draft"]):
            try:
                obj.publish(user=request.user)
                count += 1
            except ValueError:
                pass
        self.message_user(request, f"{count} item(s) published.", messages.SUCCESS)

    @admin.action(description="Unpublish selected items")
    def action_unpublish(self, request, queryset):
        count = 0
        for obj in queryset.filter(status="published"):
            obj.unpublish(user=request.user)
            count += 1
        self.message_user(request, f"{count} item(s) unpublished.", messages.WARNING)
```

### Step 2.2: Rewrite HomePageAdmin

Read `src/pages/admin/home_page.py`. Rewrite it to use `WorkflowAdminMixin` and `CompactComponentInline`. Remove ALL duplicated methods (status_badge, save_model, change_view, response_change, bulk actions). Keep only: import/export views and model-specific config (fieldsets for `name`, `is_active`).

The inline should be:

```python
class HomePageComponentInline(CompactComponentInline):
    fk_name = "home_page"
```

The admin class signature: `class HomePageAdmin(WorkflowAdminMixin, ModelAdmin):`.

Use `change_form_template = "admin/pages/shared_change_form.html"`.

### Step 2.3: Rewrite PageAdmin

Same pattern as HomePageAdmin. Read `src/pages/admin/page.py`. Rewrite to use `WorkflowAdminMixin`. The inline:

```python
class PageComponentInline(CompactComponentInline):
    fk_name = "page"
```

Use `change_form_template = "admin/pages/shared_change_form.html"`.

Keep model-specific: `prepopulated_fields`, SEO fieldset, import/export views.

### Step 2.4: Update PageComponentAdmin

Read `src/pages/admin/page_component.py`. Make `page` and `home_page` readonly:

```python
readonly_fields = ("page", "home_page")
fieldsets = (
    (None, {"fields": ("name", "component_type", "order", "is_enabled")}),
    ("Parent (read-only)", {"fields": ("page", "home_page"), "classes": ("collapse",)}),
    ("Content", {"fields": ("html_content", "css_code", "js_code", "config")}),
    ("Images", {"fields": ("image", "image_alt", "background_image"), "classes": ("collapse",)}),
    ("Data Source", {"fields": ("data_source", "data_params"), "classes": ("collapse",)}),
)
```

### Step 2.5: Update admin __init__.py

Read `src/pages/admin/__init__.py`. Import from `.base` if needed (Python will auto-discover via admin.py files, but ensure no import errors).

---

## Phase 3: Templates and Styling

### Step 3.1: Create admin-unified.css

Create `src/pages/static/pages/css/admin-unified.css`. Extract ALL the CSS from the `<style>` block in `src/pages/templates/admin/pages/homepage/change_form.html` (the workflow panel, status indicator, workflow buttons, version panel, version table, inline CodeMirror wrapper styles). This is the single source of truth for admin page styling.

### Step 3.2: Create shared_change_form.html

Create `src/pages/templates/admin/pages/shared_change_form.html` extending `admin/change_form.html`.

Block `extrahead`: load `admin-unified.css` via `{% static %}`, load `page-live-preview.js` via `{% static %}`.

Block `object-tools-items`: add "Open Live Preview" link (same markup as current homepage change_form.html line 256-262), plus `{{ block.super }}`.

Block `after_related_objects`: copy the Publishing Workflow panel and Version History panel HTML from the current homepage change_form.html (the `{% if original %}` block). Use `original.status`, `original.get_status_display`, `versions` context variable.

### Step 3.3: Simplify homepage/change_form.html

Replace the entire content of `src/pages/templates/admin/pages/homepage/change_form.html` with:

```html
{% extends "admin/pages/shared_change_form.html" %}
```

### Step 3.4: Simplify page/change_form.html

Replace the entire content of `src/pages/templates/admin/pages/page/change_form.html` with:

```html
{% extends "admin/pages/shared_change_form.html" %}
```

---

## Phase 4: Live Preview

### Step 4.1: Create preview-frontend.css

Create `src/pages/static/pages/css/preview-frontend.css`. Read these frontend CSS files and extract the relevant rules:

- `pages/src/index.css` (base: box-sizing, font-family, body)
- `pages/src/pages/Home.css` (.home-container, .home-content, .home-body, image alignment)
- `pages/src/components/PageContent/PageContent.css` (.page-content-container, .page-content, .page-body)

Add structural CSS for component rendering:
```css
.components-container { width: 100%; }
.page-component { margin-bottom: 0; }
.component-content { word-wrap: break-word; overflow-wrap: break-word; }
```

### Step 4.2: Create page-live-preview.js

Create `src/pages/static/pages/js/page-live-preview.js`. This script:

1. Binds click on `#popup-preview-btn` to open `/admin/preview-popup/` in a popup window.
2. Detects whether we are on a HomePage or Page admin form (check for `id_name` vs `id_title` field).
3. Reads the current page's API URL from the admin form (e.g., from the object's ID or slug).
4. Fetches component data from `/api/homepage/` or `/api/pages/<slug>/` via AJAX.
5. Builds preview HTML wrapping each component in `.page-component.component-{id}` > `.component-content`, with scoped `<style>` for each component's `css_code`, inside a `.components-container`.
6. Sends to popup via `postMessage({ type: 'preview-update', content: html })`.

### Step 4.3: Update preview_popup.html

Read `src/pages/templates/pages/preview_popup.html`. Replace the `theme.css` and `custom.css` stylesheet links with `preview-frontend.css`:

```html
<link rel="stylesheet" href="/static/pages/css/preview-frontend.css">
```

Keep the existing postMessage listener and page structure.

### Step 4.4: Update component_preview.html

Read `src/pages/templates/pages/component_preview.html`. Same change: replace `theme.css`/`custom.css` with `preview-frontend.css`.

---

## Phase 5: Serializer

### Step 5.1: Update PageComponentSerializer

Read `src/pages/serializers/serializers.py`. Add `"name"` and `"is_enabled"` to the `PageComponentSerializer.Meta.fields` list:

```python
fields = [
    "id", "name", "component_type", "order", "is_enabled",
    "html_content", "css_file", "css_code", "js_code", "config",
    "created_at", "updated_at",
]
```

---

## Phase 6: Frontend Sync

### Step 6.1: Update api.ts

Read `pages/src/services/api.ts`. Update the `PageComponent` interface:

Change `component_type` from `'html' | 'form' | 'google_sheet' | 'sheet'` to `'html' | 'markdown' | 'form' | 'table'`.

Add `name: string;` and `is_enabled: boolean;` fields.

### Step 6.2: Update ComponentRenderer.tsx

Read `pages/src/components/PageContent/ComponentRenderer.tsx`.

In `ComponentListRenderer`, add `is_enabled` filtering:

```typescript
const sortedComponents = [...components]
  .filter((c) => c.is_enabled)
  .sort((a, b) => a.order - b.order);
```

In `ComponentRenderer`, change the type check from:
```typescript
if (component.component_type !== 'html') {
  return null;
}
```
to:
```typescript
if (!['html', 'markdown', 'form', 'table'].includes(component.component_type)) {
  return null;
}
```

Add `data-component-name={component.name}` to the component container div.

### Step 6.3: TypeScript check

Run:
```bash
cd pages && npx tsc --noEmit
```

Fix any errors. Then:
```bash
cd pages && npm run build
```

Verify build succeeds.

---

## Phase 7: Final Verification

Run all checks:

```bash
cd src && python manage.py migrate
cd src && python manage.py test
cd pages && npx tsc --noEmit
cd pages && npm run build
```

All must pass with zero errors.

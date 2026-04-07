# Django Admin

Admin interface customization, theme configuration, and extension patterns.

## Unfold theme

The admin uses the [Unfold](https://github.com/unfoldadmin/django-unfold) theme with a custom OKLch color palette (purple primary). Configuration is in `src/core/settings/components/integrations/admin.py`.

### Base classes

All admin classes **must** inherit from `core.admin.BaseModelAdmin` or `ReadOnlyModelAdmin`, not Django's stock `ModelAdmin`. This ensures consistent theming and behavior.

```python
from core.admin import BaseModelAdmin

class MyModelAdmin(BaseModelAdmin):
    ...
```

### Sidebar organization

The admin sidebar is organized into five sections:

| Section | Models |
|---------|--------|
| Site Settings | SiteSettings, SiteMaintenanceControl, EmailServiceConfig, SMSServiceConfig, GoogleCredentialConfig |
| CMS | CMSPage, CMSBlock, CMSAsset, NewsArticle, NewsFeedSource, Menu, FooterContent |
| Events | Event, EventRegistration, Ticket, Question, CheckIn, CurrentProjectSchedule |
| Projects | Semester, Project |
| Members & Auth | Member, ContactEmail, ContactPhone, AdminInvitation, EmailAuthChallenge |

### Tab groups

Related models are grouped into tabs in the admin interface. Tab configuration is in `src/core/settings/components/integrations/admin.py`. For example, event-related models appear as tabs when viewing an event.

## Custom admin views

### Admin login

`AdminLoginView` (`src/authn/views/admin/login.py`) replaces the default Django admin login at `/admin/login/`. It integrates with the platform's auth system.

### Email campaign admin

`EmailCampaignAdmin` (`src/mail/admin/campaign.py`) provides:
- Inline recipient logs
- Campaign status display
- Gmail template import action
- Audience selection by type

### Event admin

Event admin includes:
- Registration management with filtering
- Google Sheets sync actions (registration sync, full replace)
- Schedule sync from Google Sheets
- Check-in record management

### Project admin

Semester admin includes:
- Project import from CSV
- Filtering by semester, class code, track

## CKEditor 5 integration

Rich text editing for CMS block content and email campaign bodies.

**Configuration:** `src/core/settings/components/integrations/editor.py`

- Toolbar: heading, bold, italic, link, list, image, table, blockquote, code, alignment
- File uploads: `/ckeditor5/` endpoint, restricted to staff users
- Storage: uses the active file storage backend (local or S3)

## Adding new admin pages

1. Create an admin class inheriting from `core.admin.BaseModelAdmin`
2. Register it in the app's `admin.py`
3. Add it to the appropriate sidebar section in `core/settings/components/integrations/admin.py`
4. If it should appear in a tab group with related models, add it to the tab configuration

## Related pages

- [Content Management](content-management.md) — CMS workflows
- [Member & Mail Tools](member-and-mail-tools.md) — Member and email admin
- [Architecture: Backend](../architecture/backend.md) — Settings structure

# Django Admin

Admin interface customization, theme configuration, and extension patterns.

## Unfold theme

The admin uses the [Unfold](https://github.com/unfoldadmin/django-unfold) theme with a custom OKLch color palette (purple primary). Configuration is in `src/config/settings/components/integrations/admin.py`.

### Base classes

All admin classes **must** inherit from `apps.core.admin.BaseModelAdmin` or `ReadOnlyModelAdmin`, not Django's stock `ModelAdmin`. This ensures consistent theming and behavior.

```python
from apps.core.admin import BaseModelAdmin

class MyModelAdmin(BaseModelAdmin):
    ...
```

### Sidebar organization

The admin sidebar is organized into five sections:

| Section | Models |
|---------|--------|
| Site Settings | SiteSettings, SiteMaintenanceControl, GoogleCredentialConfig, AWSCredentialConfig |
| CMS | CMSPage, CMSBlock, CMSAsset, NewsArticle, NewsFeedSource, Menu, FooterContent |
| Events | Event, EventRegistration, Ticket, Question, CheckIn, CurrentProjectSchedule |
| Projects | Semester, Project |
| Members & Auth | Member, ContactEmail, ContactPhone, AdminInvitation, EmailAuthChallenge |

### Tab groups

Related models are grouped into tabs in the admin interface. Tab configuration is in `src/config/settings/components/integrations/admin.py`. For example, event-related models appear as tabs when viewing an event.

## Custom admin views

### Admin login

`AdminLoginView` (`src/apps/authn/views/admin/login.py`) replaces the default Django admin login at `/admin/login/`. It integrates with the platform's auth system.

### Member admin — search

`MemberAdmin` (`src/apps/authn/admin/members/member.py`) keeps the default `search_fields`
(related contact email, first/middle/last name, id, organization, title) and additionally supports
**phone-number search** via an overridden `get_search_results`:

- The query is reduced to digits (`re.sub(r"\D", "", term)`), so formatted input — spaces,
  parentheses, hyphens, dots, and a leading `+` — is accepted.
- Phones are stored as **national** digits (`ContactPhone.phone_number`), so an 11-digit `1XXXXXXXXXX`
  is also tried as the national `XXXXXXXXXX`. This makes `+1 555 123 4567`, `15551234567`, the
  national `5551234567`, and partials such as `555123` / `1234567` all resolve to the same member.
- Phone matches are OR-ed into the same base queryset (so list filters still apply) and de-duplicated,
  so a member who owns several matching phones appears once.

Phone search is scoped to the member admin; the `ContactEmail` admin is unchanged, and `ContactPhone`
admin already searches `phone_number` directly. `phone_number` is already indexed; no new index was
added (a leading-wildcard `icontains` can't use a btree index, but the contact table is small — a
`pg_trgm` GIN index is a possible future optimization).

### Email campaign admin

`EmailCampaignAdmin` (`src/apps/mail/admin/campaign.py`) provides:
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

**Configuration:** `src/config/settings/components/integrations/editor.py`

- Toolbar: heading, bold, italic, link, list, image, table, blockquote, code, alignment
- File uploads: `/ckeditor5/` endpoint, restricted to staff users
- Storage: uses the active file storage backend (local or S3)

## Adding new admin pages

1. Create an admin class inheriting from `apps.core.admin.BaseModelAdmin`
2. Register it in the app's `admin.py`
3. Add it to the appropriate sidebar section in `config/settings/components/integrations/admin.py`
4. If it should appear in a tab group with related models, add it to the tab configuration

## Related pages

- [Content Management](content-management.md) — CMS workflows
- [Member & Mail Tools](member-and-mail-tools.md) — Member and email admin
- [Architecture: Backend](../architecture/backend.md) — Settings structure

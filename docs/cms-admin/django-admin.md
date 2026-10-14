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

Password guessing is bounded per account by the same lockout as member sign-in (`apps.authn.services.login_guard`: 10 failures per 15 minutes or 30 per UTC day, counted in PostgreSQL), never per client IP, so one admin's typos cannot lock out other staff on the campus network. The two password forms count separately:

- The email + password form counts on the submitted email, the same counter as the member login for that address. Anyone who knows a staff address can lock this form for it by failing on purpose (by design: an anonymous request can only be counted by the address it names).
- The remembered-admin form (it shows your name instead of an email field, and is offered to a browser holding the signed `i2g_last_admin_member` cookie from an earlier admin sign-in) counts on the member in that cookie, in a counter that no typed email or phone number can reach. Failed attempts against a staff address elsewhere do not lock it; only wrong passwords entered on that form do.

A locked form shows "Too many login attempts. Please try again later." even with the correct password, and a successful sign-in clears the counter of the form that was used. If the email + password form is locked for your address, use the remembered form in a browser you have signed in from before, or the email-code login, which this lockout never applies to. When a new admin code is refused because one was sent a moment ago and that code is still usable, the page opens the code step anyway ("If a code already reached this address, enter the most recent one below."), so requests made by someone else do not hold you on the first step. This narrows one lever and does not remove it. Someone who knows your address can still keep you out of the email-code login in two ways. The send limits (one code a minute, ten an hour per address) are shared by every code endpoint, so requests through the public sign-in can hold them; that is noisy, because each accepted request emails you. Wrong guesses from any browser use up a pending code; that is silent, causes no email, and can start from a refused request made while your code is pending, so a correct code may be answered "invalid or has expired". If that happens, the remembered form on a browser you have signed in from before is the path nobody else can interfere with; otherwise ask another administrator, and consider the off-campus edge rules in [WAF rate limits](../deployment/waf-rate-limits.md). See [Auth & Mail](../api/auth-and-mail.md#login).

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
- Inclusive start/end dates for single-day and multi-day events
- Safe prefill from an existing event when creating a new event; identity, registration availability, and sync state are reset before review
- Google Sheets sync actions (registration sync, full replace)
- Check-in record management

**Registration open** controls whether the event appears in public registration and accepts new registrations. Multiple events can be open at the same time; there is no separate featured/live Event flag. Schedule and current-project selection are managed independently through `CurrentProjectSchedule`.

### Current Project and Schedule admin

One `CurrentProjectSchedule` row per event schedule (typically per year), each with its own Google Sheet ID and
worksheet GIDs. Exactly one row is **Active**: it backs `/schedule` when no schedule is selected,
`/event/projects/` and the assistant context. All rows can be selected from CMS embed widgets and their blocks
(see [content management](content-management.md#embed-widget-blocks-and-schedule-selection)).

- **Pull Current Projects & Schedule** (changelist button) syncs the active row from its sheet
- **Sync from Google Sheets** (per-row action, also on the change form) syncs that row from its own sheet
- **Auto Sync** + interval are per row; `python manage.py sync_schedule` honours them for every row. A row that
  stops being active (you activate another schedule — a one-step change that archives the previous row — or untick
  **Active**) has Auto Sync switched off; re-enable it per row on purpose

Registration form settings use **Prompt for Phone Number** and **Verify phone**. Verification is disabled and cleared when the phone prompt is off. Registration exports provide separate **Event Start Date** and **Event End Date** columns.

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

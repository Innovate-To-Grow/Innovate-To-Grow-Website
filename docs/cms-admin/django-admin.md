# Django Admin

Admin interface customization, theme configuration, and extension patterns.

## Unfold theme

The admin uses the [Unfold](https://github.com/unfoldadmin/django-unfold) theme with a custom OKLch color palette (purple primary). Configuration is in `src/config/settings/base/integrations/admin/theme.py`.

### Base classes

All admin classes **must** inherit from `apps.core.admin.BaseModelAdmin` or `ReadOnlyModelAdmin`, not Django's stock `ModelAdmin`. This ensures consistent theming and behavior.

`BaseModelAdmin.lookup_allowed` also refuses changelist query-string lookups on secret-looking field names (`SENSITIVE_FIELD_RE`, for example `?password__startswith=a` or `?private_key__regex=…`) with `400`, so the result count can never be used to guess a stored secret one character at a time.

```python
from apps.core.admin import BaseModelAdmin

class MyModelAdmin(BaseModelAdmin):
    ...
```

### Sidebar organization

The admin sidebar is organized into five sections:

| Section | Models |
|---------|--------|
| Site Settings | SiteSettings, SiteMaintenanceControl, GoogleCredentialConfig, AWSCredentialConfig; the Request Limits page ([Request limits](../integrations/request-limits.md)) |
| CMS | CMSPage, CMSBlock, CMSAsset, NewsArticle, NewsFeedSource, Menu, FooterContent |
| Events | Event, EventRegistration, Ticket, Question, CheckIn, CurrentProjectSchedule |
| Projects | Semester, Project |
| Members & Auth | Member, ContactEmail, ContactPhone, AdminInvitation, EmailAuthChallenge |

### Tab groups

Related models are grouped into tabs in the admin interface. Tab configuration is in `src/config/settings/base/integrations/admin/tabs.py`. For example, event-related models appear as tabs when viewing an event.

## Custom admin views

### Admin login

`AdminLoginView` (`src/apps/authn/views/admin/login/view.py`) replaces the default Django admin login at `/admin/login/`. It integrates with the platform's auth system.

Password guessing is bounded per account by the same lockout as member sign-in (`apps.authn.services.login_guard`: 10 failures per 15 minutes or 30 per UTC day, counted in PostgreSQL), never per client IP, so one admin's typos cannot lock out other staff on the campus network. The two password forms count separately:

- The email + password form counts on the submitted email, the same counter as the member login for that address. Anyone who knows a staff address can lock this form for it by failing on purpose (by design: an anonymous request can only be counted by the address it names).
- The remembered-admin form (it shows your name instead of an email field, and is offered to a browser holding the signed `i2g_last_admin_member` cookie from an earlier admin sign-in) counts on the member in that cookie, in a counter that no typed email or phone number can reach. Failed attempts against a staff address elsewhere do not lock it; only wrong passwords entered on that form do.

A locked form shows "Too many login attempts. Please try again later." even with the correct password, and a successful sign-in clears the counter of the form that was used. If the email + password form is locked for your address, use the remembered form in a browser you have signed in from before, or the email-code login, which this lockout never applies to. When a new admin code is refused because one was sent a moment ago and that code is still usable, the page opens the code step anyway ("If a code already reached this address, enter the most recent one below."), so requests made by someone else do not hold you on the first step. This narrows one lever and does not remove it. Someone who knows your address can still keep you out of the email-code login in two ways. The send limits (one code a minute, ten an hour per address) are shared by every code endpoint, so requests through the public sign-in can hold them; that is noisy, because each accepted request emails you. Wrong guesses from any browser use up a pending code; that is silent, causes no email, and can start from a refused request made while your code is pending, so a correct code may be answered "invalid or has expired". If that happens, the remembered form on a browser you have signed in from before is the path nobody else can interfere with; otherwise ask another administrator, and consider the off-campus edge rules in [WAF rate limits](../deployment/waf-rate-limits.md). See [Auth & Mail](../api/auth-and-mail.md#login).

### Member and contact admin search

`MemberAdmin`, `ContactEmailAdmin` and `ContactPhoneAdmin` share `RankedSearchMixin`
(`src/apps/authn/admin/members/search.py`). It runs Django's stock search first: every word of the term must match
one of the `search_fields` (`icontains`). Members search every contact email, first/middle/last name, `id`,
organization and title. On top of that:

- **Phone numbers, only for a phone-shaped term.** `ContactPhone.phone_number` holds national digits, so a typed
  number is matched by its digits (`phone_number__contains`). That happens only when the *whole* term is digits plus
  spaces and `( ) - . +`, with at least `MIN_PHONE_DIGITS` (3) digits.
  - A leading `+1`, or the `1` of an 11-digit `1XXXXXXXXXX`, is the US country code and is dropped. So
    `+1 555 123 4567`, `15551234567`, `(555) 123-4567` and partials such as `555123` or `555` all work.
  - A term with a letter or an `@` is never a phone search. Until November 2026 the member search reduced *any*
    term to its digits, so `jdoe32@example.edu` also listed every member whose phone contains "32". The member
    pickers (20 per page) then filled up with those and never showed the member.
  - Phone matches are OR-ed in from the same base queryset, so list filters still apply. The changelist
    de-duplicates a member who owns several matching phones.
- **Exact matches first.** Results are ordered by a `search_rank` alias, then by the list's own order:
  - 0: an address equal to the term, in any letter case;
  - 1: an address that starts with the term (a single word without `@` counts as the part before the `@`:
    `jdoe` ranks `jdoe@…` above `jdoe2@…`), or, for members and phones, a phone equal to the term's digits;
  - 2: everything else.

  A column sort the user picks (`?o=`) replaces the rank. `alias()` keeps the rank out of the paginator's
  `count()`. The rank's `EXISTS` subqueries are correlated on the indexed `member_id` foreign keys. On 6,000
  members, an area-code search (`209`, every member matching) took about 57 ms for a ranked page of 50 on
  PostgreSQL 16, against 26 ms before.
- **Member pickers.** Django's `AutocompleteJsonView` calls `MemberAdmin.get_search_results`, so every
  `autocomplete_fields = ["member"]` picker (Contact Emails, Contact Phones, Event Registrations) gets the same
  results and order.
- Contact Emails has no phone search. Contact Phones searches its own `phone_number` the same way, which also makes
  formatted numbers findable there.

`phone_number` is indexed, but a leading-wildcard `contains` can't use a btree index. The contact tables are small; a
`pg_trgm` GIN index is a possible future optimization. Not changed: the `id` field still matches any part of the
Member UUID, so a short term made only of the letters a–f and digits can also match a few UUIDs.

### Member flags, list filters and the primary-email switch

Also in `src/apps/authn/admin/members/` (details in
[Member & Mail Tools](member-and-mail-tools.md#account-active-verified-and-subscribed)):

- `filters.py`: `SimpleListFilter`s built on `EXISTS` subqueries over the member's own rows, so a filter never
  duplicates a member. Members: Account active, Primary email, Unverified emails, Newsletter, Phone. Contact Emails:
  Verified (sign-in), Subscribed (newsletters), Member account; Contact Phones: Member account.
- `help_texts.py`: the "Account active" label and the help text of every flag, applied through the admin forms'
  `Meta.labels` / `Meta.help_texts` (Django uses them for read-only fields too), so no model field or migration
  changes.
- `sign_in_warning.py`: warns, never blocks, when a save, a bulk "mark unverified" or a delete leaves a member with no
  verified email or phone. `get_confirmation_diff` adds the warning as a row of the type-to-confirm page; `save_related`
  / `save_model` / the actions add a message after the write.
- `primary_switch.py` (+ `primary_switch_notes.py`, template `admin/authn/member/switch_primary.html`): the **Switch
  primary email** detail action and its page. `get_actions_detail` hides the button unless
  `user_can_manage_member` allows it, and the view re-checks, because Unfold wraps a detail-action URL only in
  `admin_view`. The write goes through `apps.authn.services.contacts.primary_switch` (member lock, fingerprint,
  history).

### Email campaign admin

`EmailCampaignAdmin` (`src/apps/mail/admin/campaign/admin.py`) provides:
- Inline recipient logs
- Campaign status display
- Gmail template import action
- **Resume paused recipients** action: sends the recipients a delivery limit paused
  ([Delivery rates](../integrations/delivery-rates.md)); the SMS campaign admin has the same action
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

The changelist's overview (Current Schedule card, **Pull** button, **Auto Sync** form, winners and project
tables) shows the **Active** row. When only one row exists it is shown even if it is not active, so a freshly
added schedule is visible before you activate it; with several rows only the active one is shown.

- **Pull Current Projects & Schedule** (changelist button) syncs the row shown in the overview from its sheet
  (the active row, or the only row when there is just one)
- **Sync from Google Sheets** (per-row action, also on the change form) syncs that row from its own sheet
- **Agenda items** (change form) are the rows of the schedule page's **Expo: Posters and Demos** and **Awards &
  Reception** tables — time, title and location, ordered by *Display order* (unique per table). Leave it blank on a
  new row to add the row at the end; rows can be swapped, shifted or moved to the other table in one save. The tables'
  *Room:* header shows the location of the first row. Syncs seed the defaults once and never overwrite your edits; delete
  every row of a table to hide it
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

**Configuration:** `src/config/settings/base/integrations/editor/__init__.py`

- Toolbar: heading, bold, italic, link, list, image, table, blockquote, code, alignment
- File uploads: `/ckeditor5/` endpoint, restricted to staff users
- Storage: uses the active file storage backend (local or S3)

## Adding new admin pages

1. Create an admin class inheriting from `apps.core.admin.BaseModelAdmin`
2. Register it in the app's `admin.py`
3. Add it to the appropriate sidebar section in `config/settings/base/integrations/admin/navigation.py`
4. If it should appear in a tab group with related models, add it to `config/settings/base/integrations/admin/tabs.py`

## Related pages

- [Content Management](content-management.md) — CMS workflows
- [Member & Mail Tools](member-and-mail-tools.md) — Member and email admin
- [Architecture: Backend](../architecture/backend.md) — Settings structure

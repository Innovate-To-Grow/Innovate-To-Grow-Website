# Legacy Event Pages → CMS Migration

The legacy Innovate to Grow per-semester event pages (Fall 2020 → Fall 2024) were migrated from the old Flask/Jinja site into **CMS-managed pages**. There is no per-page React/Django code — each page is data (CMS blocks) served by the existing catch-all CMS route. This document records the final approach and how to reproduce the import.

## What was removed (compat layer)

The earlier stopgap — a dynamic `EventArchivePage` at `/events/:eventSlug` plus eleven `*-event` → `/events/*` redirects — was deleted, since these archives are frozen:

- `pages/src/routes/EventArchivePage/` (component, configs, tests) — deleted.
- `pages/src/app/router.tsx` — removed the lazy import, the `events/:eventSlug` route, and the eleven redirect routes.
- Test references in `__tests__/{barrel-exports,lazy-routes,router-smoke}.test.ts` — updated.

`ScheduleGrid` and the rest of the `events`/`projects` features stay (used by the current-event `SchedulePage`).

## Pages

| Route (canonical, old URLs) | Slug | Title |
|---|---|---|
| `/past-events` | `past-events` | Past Events (index) |
| `/2024-fall-event` | `2024-fall-event` | Fall 2024 Event |
| `/2024-spring-event` | `2024-spring-event` | Spring 2024 Event |
| `/2023-fall-event` | `2023-fall-event` | Fall 2023 Event |
| `/2023-spring-event` | `2023-spring-event` | Spring 2023 Event |
| `/2022-fall-event` | `2022-fall-event` | Fall 2022 Event |
| `/2022-spring-event` | `2022-spring-event` | Spring 2022 Event |
| `/2021-fall-event` | `2021-fall-event` | Fall 2021 Event |
| `/2021-spring-event` | `2021-spring-event` | Spring 2021 Event |
| `/2020-fall-post-event` | `2020-fall-post-event` | Fall 2020 Event |

Routes are served by the React catch-all (`{path: '*', element: <CMSPageComponent/>}`) — no router entries needed. 2025 was intentionally out of scope.

## Block composition (per year page)

`page_css_class = event-page`, plus a per-page `page_css` for the winner/track-table coloring. Block order mirrors the legacy page:

1. **Header** (`rich_text`) — `.ea-header` back-link + subtitle.
2. **About Innovate to Grow** (`rich_text`) — the program intro (canonical copy).
3. **Winners** (`rich_text`) — award/winning-team content. *Only where the data survives.* Fall 2024 has the full colored **Track Winners** table (Track/Class/Topic/Room/Winning Team, CAP gold · CEE cyan · CSE navy); Fall 2021 has the per-track list. The other 7 semesters' winners were live from Google Sheets that are now overwritten — that data is gone (see below).
4. **Message from the Dean** (`embed`) — YouTube welcome video. *Only on pages that had one* (Fall 2024, Spring 2024, Fall 2023, Fall 2020).
5. **I2G Information** (`rich_text`) — the legacy `.event-btn` nav row (Event · Schedule · Projects & Teams `#projects` · For Attendees · For Judges · For Students · Our Partners & Sponsors).
6. **Event Schedule** (`rich_text`) — EXPO + Awards & Reception times/locations. *Where present.* Fall 2024 also has a **Presentations** track/room table.
7. **Projects & Teams** (`project_table`) — see below.

The `/past-events` index is a `rich_text` intro + a `link_list` of the nine year pages plus a **Past Projects database** link.

## The searchable `project_table` block

The legacy DataTable (search box + sortable columns + expandable Abstract/Student rows) is reproduced by a **new CMS block type `project_table`** that renders hardcoded rows through the site's existing `SheetsDataTable` component (the `.sdt-*` styles already live in the active CMS stylesheet, so it's styled on any CMS page).

- Backend: `project_table` in `BLOCK_TYPE_CHOICES` / `BLOCK_SCHEMAS` (required `rows`; optional `heading`, `caption`), migration `0016_alter_cmsblock_block_type`.
- Frontend: `pages/src/features/cms/components/blocks/content/ProjectTableBlock.tsx`, registered in `BlockRenderer`.
- Also: `import_export.py` now carries the `page_css` field (it previously dropped it), so the bundle round-trips fully.

Each page's rows are hardcoded into the block from the archived master CSV `archive/legacy/backup_old/project/Past Projects … .csv` (Year-Semester, Class, Team#, Team Name, Project Title, Organization, Industry, Abstract, Student Names) — filtered to that semester. This covers all 9 semesters.

## Data limits — what could not be reproduced

The legacy pages loaded winners, the presentation schedule, and the project table **live from two Google Sheets** at view time. Those sheets now hold only the **current** semester (Fall 2024). Verified against `I2G-Tracks`, its empty "OLD DO NOT TOUCH" tab, the archived CMS export, and the backup folder.

- **Projects** — fully recovered for all 9 semesters from the archived master CSV → hardcoded into each `project_table`.
- **Winners + presentation tracks** — only **Fall 2024** survives in the live sheet (used to build its colored Track Winners + Presentations tables) and **Fall 2021** survives as static text in the old template. The other 7 semesters' winner/presentation data is gone; those sections are omitted.
- Pre-event "Register NOW" / Zoom-instructions / event-map blocks and the legacy logo image were dropped (dead/irrelevant for an archive).

## Reproducing the import (any environment)

The bundle lives at `docs/cms-admin/past-events-import.json` (`{version, pages:[…]}`).

**Via Django admin:** CMS → Pages → Import → upload the JSON → dry-run → execute.

**Via shell:**
```bash
cd src && python manage.py shell --settings=config.settings.local -c "
import json
from apps.cms.admin.cms.page_admin.import_export import process_page_data
b = json.load(open('../docs/cms-admin/past-events-import.json'))
process_page_data(b['pages'], action='execute', default_status='published', validate_required=True)
"
```
The import upserts by slug and replaces blocks, so it is idempotent and safe to re-run. To edit content, change the JSON (or the page in admin) and re-import.

# Projects API

Past project archives and sharing. All under `/projects/`.

## Overview

The projects system stores historical project records organized by semester. Projects are imported via CSV and displayed on the frontend as a searchable archive. Users can share projects with a rate-limited sharing feature.

## Code locations

| Concern | Path |
|---------|------|
| Views | `src/projects/views/` |
| Serializers | `src/projects/serializers/` |
| Services | `src/projects/services/` |
| Models | `src/projects/models/` |
| URLs | `src/projects/urls.py` |

## Key models

| Model | Key fields |
|-------|-----------|
| `Semester` | Term label (e.g., "Fall 2024") |
| `Project` | `semester`, `class_code`, `team_number`, `team_name`, `project_title`, `organization`, `industry`, `abstract`, `student_names`, `track`, `presentation_order` |
| `PastProjectShare` | Links a user to a shared project (rate-limited) |

**Indexes:** `(semester, class_code)` and `(semester, track, presentation_order)` for efficient querying and ordering.

## Endpoints

### `GET /projects/past/`

Paginated list of past projects, grouped by semester.

**Permission:** AllowAny

**Serializer:** `SemesterWithProjectsSerializer` — returns semesters with nested project lists.

### `GET /projects/past-all/`

All past projects without pagination. Used for full-list views or exports.

**Permission:** AllowAny

### `GET /projects/{id}/`

Single project detail.

**Permission:** AllowAny

**Serializer:** `ProjectDetailSerializer`

### `POST /projects/past-shares/`

Creates a share record for a project.

**Permission:** Authenticated

**Throttle:** `PastProjectShareThrottle` — 10 requests/hour

### `GET /projects/past-shares/{id}/`

Retrieves share details.

**Permission:** Authenticated

## Data import

Projects are imported via CSV through the Django admin. The import service is at `src/projects/services/`.

CSV columns map to Project model fields. Import is triggered from the Semester admin page.

## Relationship to events

Projects displayed in the event schedule are linked via `CurrentProjectSchedule` → `Semester` → `Project`. The schedule sync service (`src/event/services/schedule_sync.py`) can also create/update Project records from Google Sheets.

## Related pages

- [Events](events.md) — Schedule display and project-event linkage
- [CMS & News](cms-and-news.md) — Project pages may be CMS-driven
- [Google Sheets Integration](../integrations/google-sheets/index.md) — Schedule sync imports project data

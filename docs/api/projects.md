# Projects API

Past project archives and sharing. All under `/projects/`.

## Overview

The projects system stores historical project records organized by semester. Projects are imported via CSV and displayed on the frontend as a searchable archive. Users can share projects with a rate-limited sharing feature.

## Code locations

| Concern | Path |
|---------|------|
| Views | `src/apps/projects/views/` |
| Serializers | `src/apps/projects/serializers/` |
| Services | `src/apps/projects/services/` |
| Models | `src/apps/projects/models/` |
| URLs | `src/apps/projects/urls.py` |

## Key models

| Model | Key fields |
|-------|-----------|
| `Semester` | Term label (e.g., "Fall 2024") |
| `Project` | `semester`, `class_code`, `team_number`, `team_name`, `project_title`, `organization`, `industry`, `abstract`, `student_names`, `track`, `presentation_order` |
| `PastProjectShare` | Versioned JSON snapshot curated by a user; public read, owner-only mutation |

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

Creates a versioned shared-project snapshot.

**Permission:** Authenticated

**Throttle:** `PastProjectShareThrottle` — 10 requests/hour

### `GET /projects/past-shares/mine/`

Lists snapshots created by the authenticated user.

**Permission:** Authenticated

### `GET /projects/past-shares/{id}/`

Publicly retrieves a shared snapshot. The response always contains its current
integer `version`.

**Permission:** AllowAny

### `PATCH /projects/past-shares/{id}/`

Owner-only optimistic update. The request must include the `version` returned by
the latest GET/PATCH. A stale update returns HTTP 409:

```json
{
  "code": "stale_snapshot",
  "detail": "This shared project changed. Refetch it before applying another edit.",
  "current": {"id": "<uuid>", "version": 4}
}
```

The frontend serializes mutations and stops/refetches on this conflict instead
of merging two whole-document updates.

### `DELETE /projects/past-shares/{id}/`

Owner-only deletion. Non-owners receive 404 so ownership is not disclosed.

## Data import

Projects are imported via CSV through the Django admin. The import service is at `src/apps/projects/services/`.

CSV columns map to Project model fields. Parsing is side-effect-free; semesters
and projects are written only inside the non-dry-run transaction. Import is
triggered from the Semester admin page.

## Relationship to events

Projects displayed in the event schedule are linked via `CurrentProjectSchedule` → `Semester` → `Project`. The schedule sync service (`src/apps/event/services/schedule_sync.py`) can also create/update Project records from Google Sheets.

## Related pages

- [Events](events.md) — Schedule display and project-event linkage
- [CMS & News](cms-and-news.md) — Project pages may be CMS-driven
- [Google Sheets Integration](../integrations/google-sheets/index.md) — Schedule sync imports project data

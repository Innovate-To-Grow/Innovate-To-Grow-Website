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

Every list orders projects newest semester first, then by class, then by team number as a number (`2` before
`10`; 2021's class-prefixed `CAP02` reads as 2) — `apps/projects/ordering.py`.

### `GET /projects/archive/`

The archive the `/past-projects` page searches: compact project rows (no abstract; `student_names` included so a list
can be searched by team member), paginated and filterable (`page`, `page_size` 1-100, `search`, `year`, `season`,
`semester`). Invalid parameters are a `400` with field errors.

**Permission:** AllowAny

### `GET /projects/past/`

Paginated list of past projects, grouped by semester (`page`, `page_size` 1-20; invalid values are a `400`). No
first-party client calls it.

**Permission:** AllowAny

**Serializer:** `SemesterWithProjectsSerializer` — returns semesters with nested project lists.

### `GET /projects/past-all/`

All past projects without pagination, server-cached for 10 minutes. No first-party client calls it (the SPA uses
`/projects/archive/` and `/projects/{id}/`).

**Permission:** AllowAny

### `GET /projects/{id}/`

Single project detail.

**Permission:** AllowAny

**Serializer:** `ProjectDetailSerializer`

The id can also be a current-semester project link (an event `CurrentProject` id) from an earlier schedule: the
response is then the team's archive project once its semester is imported, else the `CurrentProject` in the same
shape (`apps/projects/services/current_project_links.py`). A team that schedule only listed (Track `(Fall)` or
`(Spring)`: it presents in another semester) resolves to its row in the schedule it presents in, matched by class,
Team# and title. A row without a slot matches an archive project only when the title matches too, since its
schedule's semester may not be the team's.

### `POST /projects/past-shares/`

Creates a versioned shared-project snapshot.

**Permission:** Authenticated

**Throttle:** `PastProjectShareRateThrottle` — 10 requests/minute

**Limit:** 100 shares per member; the 101st is a `400` with `code: "share_limit_reached"`. A share holds at most
1,000 rows, and one member's shares at most 5,000 in all: a create or update that adds rows past that is a `400` on
`rows` (an update that does not add rows is always allowed, so a member past the bound can still edit and trim).

**Rows come from the catalog** (`apps/projects/services/share_rows.py`): each submitted row must name a published
project, by `id` or (for a row without one) by Year-Semester + Class + Team#, and is stored as the archive has it —
the text a client sends is never stored. A row naming no published project is a `400` on `rows`, except on an update
when the share already holds that row (a project removed from the archive since), which is kept as stored. Reading
a share shows the catalog's current text for every row that still resolves.

**Note and details:** `note` is rich text, at most 50,000 characters, sanitized to the share allowlist on every
write. `details_text` is read-only: shares saved by the old client still serve theirs, and a value sent on a write is
ignored.

**Name:** optional. A blank or missing `name` here or on a `PUT`, or a blank `name` sent in a `PATCH`, is replaced
with the first line of the owner's own `note` text, truncated to 60 characters, else `"Past Project Curation"`
(`apps/projects/services/share_names.py`). A `PATCH` without `name` keeps the stored name. Project details added by
"Insert projects into note" never count as the owner's text, even once "Clear formatting" has made them plain text,
so an owner's line that starts like one of their fields (`Organization: …`) is skipped as well. The name is never
taken from `rows`.

### `POST /projects/past-ai-search/`

Ranks past projects against a free-text `query` with the Bedrock model (`limit` 1-10, default 10). Answers `200` with
`available`, `query`, `results` and `usage`; `available: false` when Bedrock is not configured.

**Permission:** Authenticated

**Throttle:** `PastProjectAISearchRateThrottle` — 10 requests/minute per member

**Token budget:** charged to the member and to AI search's own global budget (separate from the public assistant's, so anonymous
assistant traffic cannot pause AI search), never to the client IP. Estimated input plus the output cap is reserved before the model call and reconciled to actual usage afterwards.
`429` with `code: "budget_exceeded"` ("AI search has reached its usage limit for now. Please try again later.") means
the member's budget or the global one is spent; `503` with `code: "budget_unavailable"` means the budget store could
not be reached; `502` with `code: "ai_search_error"` means the model call failed (nothing is charged). See
[Assistant and AI search limits](../integrations/assistant-limits.md).

### `GET /projects/past-shares/mine/`

Lists snapshots created by the authenticated user. `row_count` is counted by the database; the rows themselves are
never loaded for the list.

**Permission:** Authenticated

### `GET /projects/past-shares/{id}/`

Publicly retrieves a shared snapshot. The response always contains its current
integer `version`.

**Permission:** AllowAny

### `PATCH /projects/past-shares/{id}/`

**Throttle:** `PastProjectShareUpdateRateThrottle` — 120 requests/minute per member, shared with `PUT` and `DELETE`.

Owner-only optimistic update. The request must include the `version` returned by
the latest GET/PATCH. A stale update returns HTTP 409. This abbreviated example
shows the envelope; `current` is the complete share representation (`id`, `name`,
`rows`, `note`, `details_text`, `version`, `share_url`, `can_edit`, and
`created_at`), not a summary:

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

Owner-only deletion. Non-owners receive 404 so ownership is not disclosed. Deleting a member's account deletes
their shares too.

## Data import

Projects are imported via CSV through the Django admin. The import service is at `src/apps/projects/services/`.

CSV columns map to Project model fields. Parsing is side-effect-free; semesters
and projects are written only inside the non-dry-run transaction. Import is
triggered from the Semester admin page.

## Relationship to events

Projects displayed in the event schedule are linked via `CurrentProjectSchedule` → `Semester` → `Project`. The schedule sync service (`src/apps/event/services/schedule_sync/`) can also create/update Project records from Google Sheets.

## Related pages

- [Events](events.md) — Schedule display and project-event linkage
- [CMS & News](cms-and-news.md) — Project pages may be CMS-driven
- [Google Sheets Integration](../integrations/google-sheets/index.md) — Schedule sync imports project data

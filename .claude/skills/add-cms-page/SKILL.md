---
name: add-cms-page
description: Use this skill when asked to add a new CMS page to the Django backend. It checks for conflicts, creates the page with blocks, optionally registers the route, and verifies the result.
---

# Add CMS Page

Use this skill when the user asks to add a CMS-managed page to the site.

## Workflow

1. Determine the title, route, slug, status, CSS class, and initial blocks.
2. Check for route or slug conflicts in Django and in the frontend router.
3. Create the page and blocks with `python manage.py shell -c`.
4. Register an explicit router redirect only if the route does not already fall through to CMS.
5. Verify the page record and mention any follow-up styling or menu work.

## Checks

- Query `pages.models.CMSPage` before creating anything.
- Inspect `pages/src/app/router.tsx` and any CMS route fallthrough before editing routes.
- Stop if the route is already owned by a bespoke React page or redirect.

## References

- [Block types](references/block-types.md)

## Notes

- Prefer CMS rendering for editorial content.
- Preserve existing routes and avoid duplicate slugs.
- Keep generated `body_html` compatible with existing CMS page styles.

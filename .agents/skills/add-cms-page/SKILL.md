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

- Query `cms.models.CMSPage` before creating anything.
- Inspect `pages/src/app/router.tsx` and any CMS route fallthrough before editing routes.
- Stop if the route is already owned by a bespoke React page or redirect.

## Styling

CSS is **not** stored in the frontend codebase. All styles are managed from the Django admin:

- **Global styles**: `cms.StyleSheet` records served via the `/layout/` API. Active sheets are concatenated in `sort_order` and injected into a single `<style id="itg-server-styles">` tag by `LayoutProvider`.
- **Per-page CSS**: The `CMSPage.page_css` field. Injected into `<style id="itg-page-css">` by `CMSPageComponent` when the page loads and cleared on unmount.
- **Design tokens**: `SiteSettings.design_tokens` JSON is applied as `--itg-*` CSS custom properties on `<html>` by `LayoutProvider`.

When creating a new page that needs custom styling:
1. Add CSS to the page's `page_css` field (scoped to the page wrapper via its `page_css_class`).
2. If styles should be shared across multiple pages, create or update a `StyleSheet` record instead.
3. Use `--itg-*` design-token variables rather than hardcoded values.

The stylesheet fixture at `src/cms/fixtures/stylesheets.json` seeds the initial set of style sheets. Sort order convention: global sheets < 100, page-specific sheets >= 100.

## References

- [Block types](references/block-types.md)
- [Style sheets](references/style-sheets.md)

## Notes

- Prefer CMS rendering for editorial content.
- Preserve existing routes and avoid duplicate slugs.
- Keep generated `body_html` compatible with existing CMS page styles.
- The `CMSPageSerializer` exposes: `slug`, `route`, `title`, `page_css_class`, `page_css`, `meta_description`, `blocks`.
- The layout API (`/layout/`) returns: `menus`, `footer`, `homepage_route`, `design_tokens`, `stylesheets`.

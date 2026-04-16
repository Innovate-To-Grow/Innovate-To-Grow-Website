# Style Sheet System

## How it works

The `cms.StyleSheet` model stores named blocks of CSS in the database. Active sheets are concatenated in `sort_order` by the `/layout/` API and delivered as a single `stylesheets` string. The frontend `LayoutProvider` injects this into `<style id="itg-server-styles">` on page load.

Per-page CSS lives in `CMSPage.page_css` and is injected by `CMSPageComponent` into `<style id="itg-page-css">`.

Design tokens from `SiteSettings.design_tokens` are applied as `--itg-*` CSS custom properties on `document.documentElement`.

## Existing style sheets (from fixture)

| PK | Name | Sort | Purpose |
|----|------|------|---------|
| 1 | `global` | 10 | Shared layout, typography, buttons, cards, meta boxes, notices, pagination, loading/error states, rich content, navigation rows, grids, responsive |
| 2 | `layout-container` | 20 | Main app layout container and page loading spinner |
| 3 | `layout-menu` | 30 | Navigation menu (desktop bars, dropdowns, mobile shell, member sections, responsive) |
| 4 | `layout-footer` | 40 | Footer styles |
| 5 | `cms-blocks` | 50 | CMS block rendering (hero, FAQ, notices, CTA, image-text, contact, nav-grid, tables, numbered lists, section groups, proposal cards, Google Sheets, schedule grid, sponsor year) |
| 6 | `cms-pages` | 60 | CMS page wrapper, body classes, preview bar, content sections, info blocks, lists, capstone |
| 7 | `auth` | 70 | Authentication pages (login, register, account, profile, subscriptions, feedback) |
| 8 | `page-home` | 100 | Home page hero, showcase, and layout |
| 9 | `page-news` | 110 | News list and detail pages |
| 10 | `page-projects` | 120 | Projects list, detail, and past-projects pages |
| 11 | `page-events` | 130 | Event pages, registration, archive, post-event home |
| 12 | `page-subscribe` | 140 | Subscribe page |
| 13 | `page-misc` | 150 | Not-found, acknowledgement, magic/impersonate/ticket login pages |
| 14 | `maintenance` | 160 | Maintenance mode overlay |

## Sort order convention

- **< 100**: Global/shared sheets (loaded on every page)
- **>= 100**: Page-specific sheets (also always loaded, but logically scoped to certain pages via CSS class selectors)

## Key models and files

- Model: `src/cms/models/content/layout/style_sheet.py`
- Admin: `src/cms/admin/layout/style_sheet.py`
- Fixture: `src/cms/fixtures/stylesheets.json`
- Layout API view: `src/cms/views/views.py` (`LayoutAPIView`)
- Frontend injection: `pages/src/components/Layout/LayoutProvider/LayoutProvider.tsx`
- Per-page injection: `pages/src/components/CMS/CMSPageComponent.tsx`
- Design tokens: `SiteSettings.design_tokens` field on `cms.SiteSettings`

## Adding styles for a new page

1. If the page needs unique CSS, put it in `CMSPage.page_css` (admin: "Page CSS" fieldset).
2. If styles are shared across pages, add/update a `StyleSheet` record via admin.
3. Always use `--itg-*` design-token variables for colors, spacing, typography.
4. To seed new stylesheets in dev, add entries to `src/cms/fixtures/stylesheets.json` and run `python manage.py loaddata cms/fixtures/stylesheets.json`.

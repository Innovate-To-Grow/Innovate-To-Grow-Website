# CMS Content Workflows

## CMS pages

- Create pages in the CMS section of Django admin.
- Each page has a route, title, status, optional meta description, and `page_css_class`.
- Status stays draft until the page is ready to publish.
- Admin preview keeps draft work hidden from public routes.

## Content blocks

- Rich text, FAQ, link list, table, contact info, navigation grid, section group, proposal cards, and sheet-backed blocks remain supported.
- Blocks are ordered and rendered through the shared block renderer in the frontend.
- Export and import remain available for migrating page content between environments.

## Layout content

- Menus define navigation hierarchy and external-link behavior.
- Footer content contains CTA buttons, column content, contact HTML, and social links.
- Site settings control the effective homepage route and other global presentation choices.

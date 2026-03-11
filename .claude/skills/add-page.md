---
description: Add a new static frontend page to the project with consistent styling and admin menu registration
user_invocable: true
---

# Add Page Skill

Add a new static content page to the ITG website. Three touch points: frontend page, router, and backend route registry.

## Arguments

The user should provide:
- **Page name** (e.g., "About", "FAQs", "Partnership")
- **Content** — raw HTML from the old site, plain text, or a description
- **Route path** (optional) — defaults to kebab-case of page name (e.g., `/about`, `/faqs`)
- **Icon** (optional) — Font Awesome 4 class (e.g., `fa-info-circle`), defaults to `fa-file-text-o`

## Steps

### 1. Create the page folder

Create `pages/src/pages/<PageName>/` with 3 files:

**`<PageName>.tsx`** — React functional component:
- Internal links: `<Link to="/path">` from react-router-dom
- External links: `<a href="..." target="_blank" rel="noopener noreferrer">`
- Convert old HTML into clean semantic JSX — no inline styles, no `dangerouslySetInnerHTML`
- CSS class prefix: kebab-case of page name (e.g., `about-page`, `faqs-page`)

**`<PageName>.css`** — Scoped styles using the design system tokens below:
```css
.prefix-page { max-width: 1200px; margin: 0 auto; padding: 2rem 1rem; }
.prefix-page-title { color: #0f2d52; font-size: 2rem; margin: 0 0 2rem; }
.prefix-section-title { color: #0f2d52; font-size: 1.5rem; margin: 0 0 0.75rem; }
.prefix-text { color: #444; font-size: 1rem; line-height: 1.7; margin: 0 0 0.75rem; }
.prefix-list { color: #444; font-size: 1rem; line-height: 1.7; margin: 0.5rem 0 1.5rem 1.5rem; }
.prefix-list li { margin-bottom: 0.5rem; }
.prefix-list a, .prefix-text a { color: #0f2d52; text-decoration: none; }
.prefix-list a:hover, .prefix-text a:hover { text-decoration: underline; }

@media (max-width: 768px) {
  .prefix-page { padding: 1rem; }
  .prefix-page-title { font-size: 1.5rem; }
  .prefix-section-title { font-size: 1.25rem; }
}
```

**`index.ts`** — Barrel export:
```ts
export { PageName } from './PageName';
```

### 2. Register the route

Edit `pages/src/router/index.tsx`:
- Add import: `import { PageName } from '../pages/PageName';`
- Add route entry in the appropriate comment section

### 3. Register in backend route registry

Edit `src/pages/app_routes.py` — add an entry to the `APP_ROUTES` list:
```python
{"url": "/route-path", "title": "Page Title", "icon": "fa-icon-name"},
```

This is the **single source of truth**. The flow:
```
src/pages/app_routes.py       → Python list (edit here)
  ↓
MenuAdmin.change_view()       → injects as JSON into template context
  ↓
change_form.html              → <script>window.APP_ROUTES = {{ json }}</script>
  ↓
menu-editor.js                → reads window.APP_ROUTES for dropdown
```

No JS file changes or cache busting needed.

### 4. Verify

Run `cd pages && npm run build` to confirm TypeScript compiles.

## Key Files

| Purpose | Path |
|---------|------|
| Route registry (single source of truth) | `src/pages/app_routes.py` |
| Frontend router | `pages/src/router/index.tsx` |
| Page components | `pages/src/pages/<PageName>/` |
| Menu admin class | `src/pages/admin/layout/menu.py` |
| Admin template | `src/pages/templates/admin/pages/menu/change_form.html` |
| Menu editor JS | `src/pages/static/pages/js/menu/menu-editor.js` |

## Design System Tokens

| Token | Value |
|-------|-------|
| Primary color | `#0f2d52` |
| Body text | `#444` |
| Secondary text | `#666` |
| Error text | `#b30000` |
| Border color | `#e0e0e0` |
| Card/section bg | `#f8f9fa` |
| Border radius | `8px` |
| Line height | `1.7` |
| Container max-width (list) | `1200px` |
| Container max-width (detail) | `900px` |
| Mobile breakpoint | `768px` |
| Mobile title size | `1.5rem` |
| Filled button | `background: #0f2d52; color: #fff; padding: 0.75rem 2rem; border-radius: 4px` |
| Outlined button | `border: 1px solid #0f2d52; color: #0f2d52; padding: 0.5rem 1.25rem; border-radius: 4px` |
| Card | `border: 1px solid #e0e0e0; border-radius: 8px; background: #fff` |
| Card header | `background: #f8f9fa; border-bottom: 1px solid #e0e0e0; padding: 0.75rem 1.25rem` |
| Card body | `padding: 1.25rem` |

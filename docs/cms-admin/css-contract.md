# CSS contract for CMS content

Editors store HTML in CMS content: rich-text bodies, page CSS classes (`page_css_class`), footer HTML.
That HTML can only use classes the site styles on every page, and no deploy can rewrite what is stored.
This page lists those classes and the rules for changing them.

## Where the styles live

All of the site's CSS ships with the frontend bundle. The styles stored content relies on live in
`pages/src/styles/contract/`, which `pages/src/index.css` imports first, so every page has them:

| File | Holds |
|------|-------|
| `global/*.css` | The design system: element defaults, page head, links, `.itg-*` buttons, panels, tables, forms, pagination, tags, notices, rich content, layout helpers |
| `cms-blocks/*.css` | Block styles and the prose inside every block (`.cms-rich-text`, `.cms-prose`), plus the `body-classes.css` classes stored in rich-text HTML |
| `cms-pages.css` | Page layouts built from body HTML: the event page grid (`.event-*`) and the CMS homepage (`.post-event-home-page`, `.peh-*`) |
| `page-home.css` | Home page body classes (`.home-*`) |
| `legacy-content.css` | The legacy event pages' `.ea-*` and `.schedule-page-agenda-*` classes |

`styles/contract/index.css` imports these files in cascade order: a later file wins over an earlier one at
equal specificity. Add rules to the file that owns them instead of reordering the list.

## The class list

`pages/src/styles/contract/contract-classes.json` lists the classes stored content may carry:

- `content_html`: the classes the contract files define for editor HTML;
- `design_system`: the `.itg-*` classes editors may use in rich text.

`pages/src/__tests__/core/css-contract.test.ts` fails when a listed class loses its last rule in
`styles/contract/`.

## Changing the contract

- **Adding a class:** add the rule to the owning file and the class to `contract-classes.json`.
- **Removing or renaming a class:** run the class audit in production first and check no stored content
  uses it:

  ```bash
  cd src && python manage.py audit_css_classes --no-frontend --json
  ```

  Then change the content, the rule and the list in that order.

## Classes with no style

`docs/cms-admin/legacy-event-pages-cms-html.md` also uses `ea-back-link`, `ea-subtitle`, `ea-text`,
`event-btn-blue` and `event-buttons`. The site has had no rule for them since the UC Merced subsite restyle
(October 2026). They are harmless hooks: the text renders with the surrounding prose styles.

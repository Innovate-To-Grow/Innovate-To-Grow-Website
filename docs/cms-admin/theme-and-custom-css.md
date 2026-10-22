# Theme: design tokens and custom CSS

All of the site's CSS ships with the frontend (see [CSS contract](css-contract.md)). Two things in
**Site Settings** change it without a deploy: the design tokens and the custom CSS. Both are served at
`/api/layout/theme.css`, which every page links before the frontend's own CSS.

## How the pieces stack

The frontend's CSS sits in cascade layers. A later layer wins over an earlier one whatever the selectors'
specificity:

| Layer | Holds | Edited in |
|-------|-------|-----------|
| `itg.defaults` | fallback values for every token, first-paint defaults | the repository |
| `itg.tokens` | the design tokens (`--itg-*` custom properties) | Site Settings → Design Tokens |
| `itg.base` | reserved | — |
| `itg.components` | every stylesheet of the site | the repository |
| `itg.overrides` | the custom CSS | Site Settings → Custom CSS |
| `itg.page` | reserved | — |

So a token edit changes every rule that reads that token, and a custom CSS rule beats any rule of the site's
own CSS, even a more specific one.

## Design tokens

Site Settings shows one field per token, in a collapsed section per group (colours, typography, typography on
phones, layout, borders, effects); each field is labelled with its CSS variable and shows the default. Colours
stored as `#rrggbb` get a colour picker. A blank field means the default value, and **Reset … to the
defaults** puts back a whole group. Saving refuses a value that could break the sheet, on its field. Tokens
stored under other keys (from before this form, or added by hand) are kept as they are and shown read-only
under **Other design tokens**.

The server also leaves out any stored token that could break the sheet, with a warning in its log: keys must be
lowercase letters, digits and underscores, and values must be at most 200 characters with no `;`, braces,
`<`, `>`, backslashes or comments, and only functions from an allowlist (colour, math, gradient, easing,
transform and grid functions). A token that is missing or left out
falls back to the value in `pages/src/assets/tokens.css`.

## Custom CSS

Use it for small, site-wide corrections that can't wait for a deploy; move anything lasting into the
repository. The field is a code editor with CSS highlighting and line numbers. Saving checks it and refuses CSS
with:

- an unclosed `{` or a stray `}` (with its line and column);
- a rule or value the parser can't read (for example a malformed `url(`);
- `@import`, `@charset` or `@namespace`;
- `expression()`, the `behavior` or `-moz-binding` properties, or `javascript:` URLs;
- more than 64 KB.

The check can't catch a misspelled property: the browser ignores that declaration and nothing else.

Every save that changes the custom CSS keeps a revision (the last 20, with who saved it), listed under
**CMS → Custom CSS revisions**. To go back, select one revision there and run **Restore the selected revision
as the live custom CSS**; the restore is itself kept as a new revision.

## When changes show

The sheet is cached for five minutes, in the server and in browsers and the CDN. Saving Site Settings clears
the server's copy, so a change reaches visitors within five minutes. The CDN may keep serving the last copy
for up to a day while it fetches the new one, and for up to a week if the backend is down; the frontend's
fallback tokens cover a visitor who gets no sheet at all.

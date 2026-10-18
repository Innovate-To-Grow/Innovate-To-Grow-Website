/**
 * Class list for the wrapper that CMS blocks render into.
 *
 * `cms-page` is always present so the block stack and shared block styles
 * apply on every CMS surface (pages, admin block preview, embeds); the page's
 * own `page_css_class` is added next to it for page-specific styling.
 */
export function cmsPageClassName(pageCssClass?: string | null): string {
  const classes = new Set(['cms-page']);
  for (const name of (pageCssClass || '').split(/\s+/)) {
    if (name) classes.add(name);
  }
  return Array.from(classes).join(' ');
}

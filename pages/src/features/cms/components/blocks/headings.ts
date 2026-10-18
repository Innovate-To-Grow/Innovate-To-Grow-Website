/**
 * Heading helpers shared by the CMS blocks.
 *
 * Editors pick a heading level per block (sometimes stored as a string such as
 * "1"). The level decides both the element and which design-system title class
 * it gets, so a level-1 block heading looks like every other page title.
 */

export type CMSHeadingLevel = 1 | 2 | 3 | 4 | 5 | 6;

export function normalizeHeadingLevel(value: unknown, fallback: CMSHeadingLevel = 2): CMSHeadingLevel {
  const level = Number(value);
  if (Number.isInteger(level) && level >= 1 && level <= 6) {
    return level as CMSHeadingLevel;
  }
  return fallback;
}

/**
 * Page title (h1) of a CMS page: the global page title plus CMS block spacing.
 * As on the reference site there is no rule under it.
 */
export const CMS_PAGE_TITLE_CLASS = 'itg-page-title cms-page-title';

/** h2 = 28px section title, h3 = 24px subsection title, h4-h6 = the theme's 20px h4. */
export function headingClassForLevel(level: CMSHeadingLevel): string {
  if (level === 1) return CMS_PAGE_TITLE_CLASS;
  if (level === 2) return 'itg-section-title';
  if (level === 3) return 'itg-subsection-title';
  return 'cms-minor-title';
}

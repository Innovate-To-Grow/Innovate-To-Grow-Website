export const SECTION_TITLES_KEY = 'section_titles';

export const HIDDEN_SECTION_SELECTORS: Record<string, string> = {
  // CMS block headings, and the header (title, meta line, lede) of app-route pages that mark one.
  [SECTION_TITLES_KEY]: '.section-title, [data-embed-section="page-header"]',
  schedule_header: '[data-embed-section="schedule-header"]',
  schedule_winners: '[data-embed-section="schedule-winners"]',
  schedule_expo: '[data-embed-section="schedule-expo"]',
  schedule_presentations: '[data-embed-section="schedule-presentations"]',
  schedule_awards: '[data-embed-section="schedule-awards"]',
  schedule_projects: '[data-embed-section="schedule-projects"]',
};

const TRUE_VALUES = new Set(['1', 'true', 'yes', 'on']);

export function isTruthyParam(value: string | null): boolean {
  return TRUE_VALUES.has((value || '').toLowerCase());
}

export function parseHiddenSectionsParam(value: string | null): string[] {
  if (!value) return [];
  return value
    .split(',')
    .map((key) => key.trim())
    .filter(Boolean);
}

export function normalizeHiddenSections(keys: Array<string | undefined | null>): string[] {
  const selected = new Set<string>();
  keys.forEach((key) => {
    if (key && HIDDEN_SECTION_SELECTORS[key]) {
      selected.add(key);
    }
  });
  return Array.from(selected);
}

/**
 * Section headings inside an app-route page (the builders' "Search Tables"), which "Section titles" also hides.
 * Hidden from sight only: they stay in the page's outline and remain focus targets (a builder focuses "Search
 * Tables" after a retry), so they are clipped like .sr-only rather than removed.
 */
export const VISUALLY_HIDDEN_SECTION_SELECTORS: Record<string, string> = {
  [SECTION_TITLES_KEY]: '[data-embed-section="section-title"]',
};

const VISUALLY_HIDDEN_CSS = [
  'position: absolute',
  'width: 1px',
  'height: 1px',
  'margin: 0',
  'padding: 0',
  'overflow: hidden',
  'clip-path: inset(50%)',
  'white-space: nowrap',
  'border: 0',
]
  .map((declaration) => `${declaration} !important;`)
  .join(' ');

export function buildHiddenSectionsCss(keys: string[]): string {
  return keys
    .flatMap((key) => {
      const visuallyHidden = VISUALLY_HIDDEN_SECTION_SELECTORS[key];
      return [
        `${HIDDEN_SECTION_SELECTORS[key]} { display: none !important; }`,
        ...(visuallyHidden ? [`${visuallyHidden} { ${VISUALLY_HIDDEN_CSS} }`] : []),
      ];
    })
    .join('\n');
}

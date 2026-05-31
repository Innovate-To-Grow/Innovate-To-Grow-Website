export const SECTION_TITLES_KEY = 'section_titles';

export const HIDDEN_SECTION_SELECTORS: Record<string, string> = {
  [SECTION_TITLES_KEY]: '.section-title',
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

export function buildHiddenSectionsCss(keys: string[]): string {
  return keys.map((key) => `${HIDDEN_SECTION_SELECTORS[key]} { display: none !important; }`).join('\n');
}

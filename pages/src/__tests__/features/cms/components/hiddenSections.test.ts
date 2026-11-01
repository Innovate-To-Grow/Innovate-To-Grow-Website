import {describe, expect, it} from 'vitest';

import {SECTION_TITLES_KEY, buildHiddenSectionsCss, HIDDEN_SECTION_SELECTORS} from '@/features/cms/components/hiddenSections';

describe('hidden section presets', () => {
  it('hides block section titles and app-route page headers with "Section titles"', () => {
    document.body.innerHTML = `
      <h2 class="section-title">Block heading</h2>
      <h1 class="itg-page-title" data-embed-section="page-header">Current Projects</h1>
      <p class="itg-lead" data-embed-section="page-header">Lede</p>
      <h2 class="itg-section-title">Kept</h2>`;
    const selector = HIDDEN_SECTION_SELECTORS[SECTION_TITLES_KEY];

    const hidden = Array.from(document.querySelectorAll(selector)).map((node) => node.textContent);

    expect(hidden).toEqual(['Block heading', 'Current Projects', 'Lede']);
    expect(buildHiddenSectionsCss([SECTION_TITLES_KEY])).toBe(`${selector} { display: none !important; }`);
    document.body.innerHTML = '';
  });
});

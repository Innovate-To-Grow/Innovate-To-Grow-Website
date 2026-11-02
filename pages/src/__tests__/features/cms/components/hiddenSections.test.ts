import {afterEach, describe, expect, it} from 'vitest';

import {
  SECTION_TITLES_KEY,
  buildHiddenSectionsCss,
  HIDDEN_SECTION_SELECTORS,
  VISUALLY_HIDDEN_SECTION_SELECTORS,
} from '@/features/cms/components/hiddenSections';

describe('hidden section presets', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('hides block section titles and app-route page headers with "Section titles"', () => {
    document.body.innerHTML = `
      <h2 class="section-title">Block heading</h2>
      <h1 class="itg-page-title" data-embed-section="page-header">Current Projects</h1>
      <p class="itg-lead" data-embed-section="page-header">Lede</p>
      <h2 class="itg-section-title">Kept</h2>
      <h2 data-embed-section="section-title">Search Tables</h2>`;
    const selector = HIDDEN_SECTION_SELECTORS[SECTION_TITLES_KEY];

    const hidden = Array.from(document.querySelectorAll(selector)).map((node) => node.textContent);

    expect(hidden).toEqual(['Block heading', 'Current Projects', 'Lede']);
    expect(buildHiddenSectionsCss([SECTION_TITLES_KEY]).split('\n')[0]).toBe(`${selector} { display: none !important; }`);
  });

  it('also hides builder section headings from sight only, so they stay headings and focus targets', () => {
    document.body.innerHTML = `
      <h2 data-embed-section="section-title">Search Tables</h2>
      <h2 class="past-projects-action-bar-title">Kept</h2>`;
    const selector = VISUALLY_HIDDEN_SECTION_SELECTORS[SECTION_TITLES_KEY];
    expect(Array.from(document.querySelectorAll(selector)).map((node) => node.textContent)).toEqual(['Search Tables']);

    const [, visuallyHidden] = buildHiddenSectionsCss([SECTION_TITLES_KEY]).split('\n');
    expect(visuallyHidden).toBe(
      '[data-embed-section="section-title"] { position: absolute !important; width: 1px !important; ' +
        'height: 1px !important; margin: 0 !important; padding: 0 !important; overflow: hidden !important; ' +
        'clip-path: inset(50%) !important; white-space: nowrap !important; border: 0 !important; }',
    );
    expect(visuallyHidden).not.toContain('display');
  });

  it('leaves section headings alone for the other presets', () => {
    const css = buildHiddenSectionsCss(['schedule_header']);

    expect(css).toBe('[data-embed-section="schedule-header"] { display: none !important; }');
    expect(css).not.toContain('section-title');
  });
});

import {describe, expect, it} from 'vitest';

import {
  CMS_PAGE_TITLE_CLASS,
  headingClassForLevel,
  normalizeHeadingLevel,
} from '@/features/cms/components/blocks/headings';

describe('normalizeHeadingLevel', () => {
  it('accepts heading levels 1-6 given as numbers or strings', () => {
    expect(normalizeHeadingLevel(1)).toBe(1);
    expect(normalizeHeadingLevel('3')).toBe(3);
    expect(normalizeHeadingLevel(6)).toBe(6);
  });

  it('falls back for missing, zero, fractional or out-of-range values', () => {
    expect(normalizeHeadingLevel(undefined)).toBe(2);
    expect(normalizeHeadingLevel(0)).toBe(2);
    expect(normalizeHeadingLevel(2.5)).toBe(2);
    expect(normalizeHeadingLevel(7)).toBe(2);
    expect(normalizeHeadingLevel('h1')).toBe(2);
    expect(normalizeHeadingLevel(null, 4)).toBe(4);
  });
});

describe('headingClassForLevel', () => {
  it('maps levels to the design-system title classes', () => {
    expect(headingClassForLevel(1)).toBe(CMS_PAGE_TITLE_CLASS);
    expect(CMS_PAGE_TITLE_CLASS).toBe('itg-page-title cms-page-title');
    expect(headingClassForLevel(2)).toBe('itg-section-title');
    expect(headingClassForLevel(3)).toBe('itg-subsection-title');
    // h4-h6 use the reference theme's 20px h4 style.
    expect(headingClassForLevel(4)).toBe('cms-minor-title');
    expect(headingClassForLevel(6)).toBe('cms-minor-title');
  });
});

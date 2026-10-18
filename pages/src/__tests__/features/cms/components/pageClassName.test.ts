import {describe, expect, it} from 'vitest';

import {cmsPageClassName} from '@/features/cms/components/pageClassName';

describe('cmsPageClassName', () => {
  it('always includes cms-page', () => {
    expect(cmsPageClassName()).toBe('cms-page');
    expect(cmsPageClassName('')).toBe('cms-page');
    expect(cmsPageClassName(null)).toBe('cms-page');
  });

  it('adds the page css class next to cms-page without duplicates', () => {
    expect(cmsPageClassName('submission-page')).toBe('cms-page submission-page');
    expect(cmsPageClassName('cms-page')).toBe('cms-page');
    expect(cmsPageClassName('  home-page   extra  ')).toBe('cms-page home-page extra');
  });
});

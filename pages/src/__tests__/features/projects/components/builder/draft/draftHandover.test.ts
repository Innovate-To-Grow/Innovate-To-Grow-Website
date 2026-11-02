import {afterEach, describe, expect, it} from 'vitest';

import {
  draftHandoverHref,
  isEmbeddedBuilder,
  readDraftHandover,
} from '@/features/projects/components/builder/draft/draftHandover';

const ID_A = '11111111-1111-4111-8111-111111111111';
const ID_B = '22222222-2222-4222-8222-222222222222';

describe('draftHandover', () => {
  afterEach(() => window.history.replaceState(null, '', '/'));

  it('links the full Past Projects page with the draft project ids in the fragment, once each', () => {
    expect(draftHandoverHref([{id: ID_A}, {id: ID_B}, {id: ID_A}, {id: ''}, {}])).toBe(
      `/past-projects#curation-draft=${ID_A},${ID_B}`,
    );
    expect(draftHandoverHref([])).toBe('/past-projects');
  });

  it('links the builder page it is given, for the All Projects widget', () => {
    expect(draftHandoverHref([{id: ID_A}, {id: ID_B}], '/all-projects')).toBe(
      `/all-projects#curation-draft=${ID_A},${ID_B}`,
    );
    expect(draftHandoverHref([{}], '/all-projects')).toBe('/all-projects');
  });

  it('reads the ids back, dropping anything that is not a project id', () => {
    expect(readDraftHandover(`#curation-draft=${ID_A},${ID_B},${ID_A},nope,../x`)).toEqual([ID_A, ID_B]);
    expect(readDraftHandover('#curation-draft=')).toEqual([]);
    expect(readDraftHandover('#other=1')).toBeNull();
    expect(readDraftHandover('')).toBeNull();
  });

  it('tells the widget (an /_embed/ page) from the site', () => {
    expect(isEmbeddedBuilder()).toBe(false);
    window.history.replaceState(null, '', '/_embed/test-past');
    expect(isEmbeddedBuilder()).toBe(true);
  });
});

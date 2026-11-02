import {describe, expect, it} from 'vitest';

import {resolveProjectBackTarget} from '@/routes/ProjectDetailPage/projectBackTarget';

describe('resolveProjectBackTarget', () => {
  it.each([
    ['/current-projects?page=2', 'Back to Current Projects'],
    ['/presenting-teams', 'Back to Presenting Teams'],
    ['/past-projects', 'Back to Past Projects'],
    ['/all-projects?value=water', 'Back to All Projects'],
    ['/schedule#expo', 'Back to Event Schedule'],
  ])('returns to the list that opened the page (%s), as the visitor left it', (from, label) => {
    expect(resolveProjectBackTarget({from}, false)).toEqual({href: from, label, openedFromList: true});
  });

  it('falls back to the list the project belongs to when no known list opened it', () => {
    expect(resolveProjectBackTarget({from: '/news'}, true)).toEqual({
      href: '/past-projects',
      label: 'Back to Past Projects',
      openedFromList: false,
    });
    expect(resolveProjectBackTarget(null, false)).toEqual({
      href: '/current-projects',
      label: 'Back to Current Projects',
      openedFromList: false,
    });
  });
});

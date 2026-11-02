import {describe, expect, it} from 'vitest';

import {getExportFileBaseName} from '@/features/projects/components/shared/utils/shareHelpers';

describe('getExportFileBaseName', () => {
  it('starts with the given prefix, then the title as a slug', () => {
    expect(getExportFileBaseName('  CSE capstones for Bob! ', 'past-projects')).toBe(
      'past-projects-cse-capstones-for-bob',
    );
    expect(getExportFileBaseName('Spring & Fall picks', 'projects')).toBe('projects-spring-fall-picks');
  });

  it('is the prefix alone when the title has nothing to slug', () => {
    expect(getExportFileBaseName('', 'projects')).toBe('projects');
    expect(getExportFileBaseName('  ***  ', 'past-projects')).toBe('past-projects');
  });
});

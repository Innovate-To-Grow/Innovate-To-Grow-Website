import {describe, expect, it} from 'vitest';

import {curationBranding} from '@/features/projects/components/merged/list/curationBranding';

describe('curationBranding', () => {
  it('names a curation holding a current-semester project as All Projects', () => {
    expect(curationBranding([{catalog: 'archive'}, {catalog: 'current'}])).toEqual({
      eyebrow: 'Curation · All Projects',
      exportHeading: 'Innovate to Grow Projects',
      filePrefix: 'projects',
    });
  });

  it('keeps the Past Projects names for archive projects only, and for rows from before the catalog field', () => {
    for (const rows of [[{catalog: 'archive' as const}, {}], [{}], []]) {
      expect(curationBranding(rows)).toEqual({eyebrow: 'Curation · Past Projects', filePrefix: 'past-projects'});
    }
  });
});

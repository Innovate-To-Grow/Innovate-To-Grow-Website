import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  PROJECT_DETAIL_CACHE_TTL_MS,
  readCachedProjectDetail,
  rememberProjectDetail,
} from '@/features/projects/api/projectDetailCache';
import type {ProjectDetail} from '@/features/projects/api';

const detail = (id: string): ProjectDetail => ({
  id,
  project_title: `Project ${id}`,
  team_name: 'Team',
  team_number: '101',
  organization: 'Org',
  industry: 'Energy',
  abstract: `Abstract of ${id}`,
  student_names: 'Ada Lovelace',
  class_code: 'CAP',
  track: null,
  presentation_order: null,
  semester_label: '2025-1 Spring',
});

describe('project detail cache', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns details until they expire', () => {
    const now = vi.spyOn(Date, 'now').mockReturnValue(1_000);
    rememberProjectDetail(detail('expiring'));

    expect(readCachedProjectDetail('expiring')).toMatchObject({abstract: 'Abstract of expiring'});
    now.mockReturnValue(1_000 + PROJECT_DETAIL_CACHE_TTL_MS);
    expect(readCachedProjectDetail('expiring')).toBeNull();
    expect(readCachedProjectDetail('never-loaded')).toBeNull();
  });

  it('keeps a bounded number of projects, dropping the oldest first', () => {
    rememberProjectDetail(detail('oldest'));
    rememberProjectDetail(detail('refreshed'));
    for (let index = 0; index < 299; index += 1) {
      rememberProjectDetail(detail(`filler-${index}`));
      // Loading a project again makes it the newest.
      if (index === 0) rememberProjectDetail(detail('refreshed'));
    }

    expect(readCachedProjectDetail('oldest')).toBeNull();
    expect(readCachedProjectDetail('refreshed')).not.toBeNull();
    expect(readCachedProjectDetail('filler-298')).not.toBeNull();
  });
});

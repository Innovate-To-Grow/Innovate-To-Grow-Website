import {describe, expect, it} from 'vitest';

import {
  getSharedLinkDisplayName,
  getSharedLinkResultsLabel,
  getSharedLinkSearchText,
} from '@/features/auth/components/sections/internal/sharedLinkUtils';
import type {PastProjectShareSummary} from '@/features/projects/api';

const share = (overrides: Partial<PastProjectShareSummary> = {}): PastProjectShareSummary => ({
  id: 'share-1',
  name: 'Spring finalists',
  note: '',
  version: 1,
  share_url: 'https://example.test/past-projects/share-1',
  row_count: 3,
  created_at: '2026-06-05T00:00:00Z',
  ...overrides,
});

describe('sharedLinkUtils', () => {
  it('shows a stored name, or the default curation title for a blank one', () => {
    expect(getSharedLinkDisplayName(share())).toBe('Spring finalists');
    expect(getSharedLinkDisplayName(share({name: '   '}))).toBe('Past Project Curation');
  });

  it('labels the result count', () => {
    expect(getSharedLinkResultsLabel(share({row_count: 1}))).toBe('1 result');
    expect(getSharedLinkResultsLabel(share({row_count: 14}))).toBe('14 results');
  });

  it('searches the title the list shows, not the raw stored name', () => {
    expect(getSharedLinkSearchText(share({name: ''}))).toContain('past project curation');
    expect(getSharedLinkSearchText(share())).toContain('spring finalists');
  });
});

import {describe, expect, it} from 'vitest';

import {shouldMountWidget} from '@/features/assistant/shouldMountWidget';

describe('shouldMountWidget', () => {
  it('returns false for the block-preview route', () => {
    expect(shouldMountWidget('/_block-preview', '')).toBe(false);
  });

  it('returns false for embed routes', () => {
    expect(shouldMountWidget('/_embed/abc', '')).toBe(false);
    expect(shouldMountWidget('/_embed/some/deep/path', '?x=1')).toBe(false);
  });

  it('returns false when the _isolated flag is present', () => {
    expect(shouldMountWidget('/foo', '?_isolated')).toBe(false);
    expect(shouldMountWidget('/', '?_isolated=1')).toBe(false);
    expect(shouldMountWidget('/', '?a=1&_isolated')).toBe(false);
  });

  it('returns true for the homepage', () => {
    expect(shouldMountWidget('/', '')).toBe(true);
  });

  it('returns true for normal routes', () => {
    expect(shouldMountWidget('/news', '?page=2')).toBe(true);
    expect(shouldMountWidget('/projects/123', '')).toBe(true);
  });

  it('does not treat a path that merely contains _embed elsewhere as isolated', () => {
    expect(shouldMountWidget('/blog/_embed-tips', '')).toBe(true);
  });
});

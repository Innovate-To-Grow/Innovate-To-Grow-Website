import {describe, expect, it} from 'vitest';
import {normalizeScheduleId} from '@/features/cms/components/embedScheduleId';

describe('normalizeScheduleId', () => {
  it('returns a lower-cased canonical UUID', () => {
    expect(normalizeScheduleId('  6F1D2C3B-4A5E-4F60-8A9B-0C1D2E3F4A5B ')).toBe(
      '6f1d2c3b-4a5e-4f60-8a9b-0c1d2e3f4a5b',
    );
  });

  it('rejects anything that is not a UUID', () => {
    for (const value of [null, undefined, '', 'abc', '123', '6f1d2c3b4a5e4f608a9b0c1d2e3f4a5b', 'x'.repeat(36)]) {
      expect(normalizeScheduleId(value)).toBeNull();
    }
  });
});

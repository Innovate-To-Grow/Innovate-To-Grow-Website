import {describe, it, expect} from 'vitest';
import {formatSemesterLabel} from './semester';

describe('formatSemesterLabel', () => {
  it('strips the -1 suffix from spring labels', () => {
    expect(formatSemesterLabel('2026-1 Spring')).toBe('2026 Spring');
  });

  it('strips the -2 suffix from fall labels', () => {
    expect(formatSemesterLabel('2025-2 Fall')).toBe('2025 Fall');
  });

  it('leaves already-clean labels unchanged', () => {
    expect(formatSemesterLabel('2026 Spring')).toBe('2026 Spring');
  });

  it('passes empty strings through', () => {
    expect(formatSemesterLabel('')).toBe('');
  });

  it('passes non-matching labels through', () => {
    expect(formatSemesterLabel('TBD')).toBe('TBD');
    expect(formatSemesterLabel('Spring 2026')).toBe('Spring 2026');
  });

  it('does not mangle multi-digit suffixes', () => {
    expect(formatSemesterLabel('2026-12 Other')).toBe('2026-12 Other');
  });
});

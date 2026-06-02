import {describe, it, expect} from 'vitest';
import {formatSemesterLabel, semesterParamToLabel} from './semester';

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

describe('semesterParamToLabel', () => {
  it('maps a fall param to the formatted label', () => {
    expect(semesterParamToLabel('2024-fall')).toBe('2024 Fall');
  });

  it('maps a spring param to the formatted label', () => {
    expect(semesterParamToLabel('2021-spring')).toBe('2021 Spring');
  });

  it('is case-insensitive and trims whitespace', () => {
    expect(semesterParamToLabel('  2020-FALL ')).toBe('2020 Fall');
  });

  it('matches the output of formatSemesterLabel for round-tripping', () => {
    expect(semesterParamToLabel('2024-fall')).toBe(formatSemesterLabel('2024-2 Fall'));
    expect(semesterParamToLabel('2024-spring')).toBe(formatSemesterLabel('2024-1 Spring'));
  });

  it('returns null for malformed or unknown input', () => {
    expect(semesterParamToLabel('')).toBeNull();
    expect(semesterParamToLabel('2024')).toBeNull();
    expect(semesterParamToLabel('2024-summer')).toBeNull();
    expect(semesterParamToLabel('fall-2024')).toBeNull();
  });
});

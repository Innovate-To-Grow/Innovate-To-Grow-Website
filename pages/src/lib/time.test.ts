import {describe, expect, it} from 'vitest';

import {addMinutes} from './time';

describe('addMinutes', () => {
  it('adds minutes within the same hour', () => {
    expect(addMinutes('9:00', 30)).toBe('9:30');
  });

  it('rolls over to next hour', () => {
    expect(addMinutes('9:45', 30)).toBe('10:15');
  });

  it('wraps past 12', () => {
    expect(addMinutes('12:30', 45)).toBe('1:15');
  });

  it('handles zero minutes', () => {
    expect(addMinutes('10:00', 0)).toBe('10:00');
  });

  it('handles exactly 60 minutes', () => {
    expect(addMinutes('3:00', 60)).toBe('4:00');
  });

  it('handles more than 60 minutes', () => {
    expect(addMinutes('1:00', 90)).toBe('2:30');
  });

  it('pads single-digit minutes', () => {
    expect(addMinutes('5:00', 5)).toBe('5:05');
  });

  it('handles multiple hour wraps', () => {
    expect(addMinutes('11:00', 120)).toBe('1:00');
  });
});

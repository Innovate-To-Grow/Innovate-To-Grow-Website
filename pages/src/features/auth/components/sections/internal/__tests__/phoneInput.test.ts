import {describe, expect, it} from 'vitest';

import {formatE164ForDisplay, formatNationalInputDisplay} from '../phoneInput';

describe('formatE164ForDisplay', () => {
  it('returns an empty string for an empty value', () => {
    expect(formatE164ForDisplay('')).toBe('');
  });

  it('formats a US E.164 number into the national display form', () => {
    expect(formatE164ForDisplay('+12025550123')).toBe(formatNationalInputDisplay('2025550123'));
  });

  it('formats a bare 10-digit national number', () => {
    expect(formatE164ForDisplay('2025550123')).toBe(formatNationalInputDisplay('2025550123'));
  });

  it('returns the original value unchanged when it is not a US phone number', () => {
    expect(formatE164ForDisplay('not-a-phone')).toBe('not-a-phone');
  });
});
